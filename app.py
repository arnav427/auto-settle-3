import json
import time
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from auto_settle import detector, fraud, llm, media as media_mod
from auto_settle.audit import AuditLog
from auto_settle.config import DAMAGE_TYPES, SEVERITIES, Guardrails
from auto_settle.costs import load_parts
from auto_settle.models import Detection
from auto_settle.pipeline import evaluate
from auto_settle.settlement import Settlement, inr

ROOT = Path(__file__).parent
SEEN = ROOT / "data" / "seen_images.json"
G = Guardrails()

st.set_page_config(page_title="Auto-Settle AI", layout="wide")
st.title("Auto-Settle AI: video-to-cash motor claims")

ss = st.session_state

with st.sidebar:
    st.header("Settings")
    mode = st.radio("Damage detector", ["Ollama vision model", "Demo (offline, simulated)"])
    host = st.text_input("Ollama host", llm.DEFAULT_HOST)
    vision_model = st.text_input("Vision model", "qwen2.5vl:7b")
    chat_model = st.text_input("Chat polish model (optional)", "")
    check_dupes = st.checkbox("Check for images reused from earlier claims", True)
    if st.button("Reset demo state"):
        SEEN.unlink(missing_ok=True)
        ss.clear()
        st.rerun()
    st.caption(
        f"Guardrails: cash offer {G.floor_pct:.0%} to {G.ceiling_pct:.0%} of garage estimate; "
        f"auto-settle up to {inr(G.auto_limit)}; min confidence {G.min_confidence:.0%}."
    )

files = st.file_uploader(
    "Upload photos or a short video of the damage",
    type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "avi", "mkv"],
    accept_multiple_files=True,
)

if st.button("Analyse damage", type="primary", disabled=not files):
    ss.clear()
    try:
        with st.spinner("Reading media and detecting damage..."):
            items = media_mod.load_uploads([(f.name, f.getvalue()) for f in files])
            if mode.startswith("Ollama"):
                dets, dropped = detector.detect_ollama(items, vision_model, host)
            else:
                dets, dropped = detector.detect_demo(items)
    except Exception as e:
        st.error(f"Could not analyse the upload: {e}")
        st.stop()
    ss.claim_id = f"CLM-{uuid.uuid4().hex[:8].upper()}"
    ss.audit = AuditLog(ss.claim_id, ROOT / "data" / "audit" / f"{ss.claim_id}.jsonl")
    ss.media, ss.dets, ss.dropped = items, dets, dropped
    ss.flags = fraud.check(items, SEEN if check_dupes else None)
    ss.settlement = None
    ss.chat = []
    ss.audit.add("system", "claim_received", {"files": [f.name for f in files], "detector": mode, "frames": len(items)})
    ss.audit.add("ai", "damage_detected", {"detections": [vars(d) for d in dets], "dropped": dropped})
    for f in ss.flags:
        ss.audit.add("system", "fraud_flag", vars(f))

if "claim_id" not in ss:
    st.info("Upload images or a video and click Analyse damage.")
    st.stop()

audit: AuditLog = ss.audit
st.subheader(f"Claim {ss.claim_id}")
if mode.startswith("Demo"):
    st.warning("Demo mode: detections are simulated, not real model output.")

cols = st.columns(min(len(ss.media), 4))
for i, m in enumerate(ss.media):
    cols[i % len(cols)].image(m.image, caption=m.name, use_container_width=True)

st.markdown("**Detected damage** (the reviewer can correct this table before pricing)")
locked = ss.settlement is not None
frame = pd.DataFrame([vars(d) for d in ss.dets], columns=["component", "damage_type", "severity", "confidence", "frames"])
edited = st.data_editor(
    frame,
    num_rows="dynamic",
    disabled=locked,
    use_container_width=True,
    column_config={
        "component": st.column_config.SelectboxColumn(options=list(load_parts()), required=True),
        "damage_type": st.column_config.SelectboxColumn(options=list(DAMAGE_TYPES), required=True),
        "severity": st.column_config.SelectboxColumn(options=list(SEVERITIES), required=True),
        "confidence": st.column_config.NumberColumn(min_value=0.0, max_value=1.0, step=0.05),
        "frames": st.column_config.NumberColumn(disabled=True),
    },
    key="dets_editor",
)
dets = [
    Detection(r.component, r.damage_type, r.severity, float(r.confidence if pd.notna(r.confidence) else 1.0))
    for r in edited.itertuples()
    if pd.notna(r.component) and pd.notna(r.damage_type) and pd.notna(r.severity)
]
if ss.dropped:
    st.caption(f"Ignored model output outside the known vocabulary: {', '.join(ss.dropped)}")

result = evaluate(dets, ss.flags, G)
c = result.cost

st.markdown("**Repair estimate**")
st.dataframe(
    pd.DataFrame(
        [
            {
                "component": i.component,
                "damage": f"{i.damage_type} ({i.severity})",
                "parts": i.parts,
                "paint": i.paint,
                "labour": i.labour,
                "total": i.total,
            }
            for i in c.items
        ]
    ),
    use_container_width=True,
    hide_index=True,
)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Garage estimate (incl. GST)", inr(c.estimate))
m2.metric("Estimate range", f"{inr(c.low)} to {inr(c.high)}")
m3.metric("Allowed cash floor", inr(result.floor))
m4.metric("Allowed cash ceiling", inr(result.ceiling))

for f in ss.flags:
    (st.error if f.blocking else st.warning)(f"{f.code}: {f.message}")


def escalation_packet(reasons: list) -> dict:
    return {
        "claim_id": ss.claim_id,
        "reasons": reasons,
        "detections": [vars(d) for d in dets],
        "estimate": c.estimate,
        "transcript": ss.chat,
        "audit": audit.entries,
    }


def show_escalation(reasons: list) -> None:
    st.error("Escalated to a human claims adjuster")
    for r in reasons:
        st.write(f"- {r}")
    st.download_button("Download case packet", json.dumps(escalation_packet(reasons), indent=2), f"{ss.claim_id}.json")


if result.escalate and not locked:
    if not ss.get("escalation_logged"):
        audit.add("system", "escalated", {"reasons": result.reasons})
        fraud.register(ss.media, ss.claim_id, SEEN)
        ss.escalation_logged = True
    show_escalation(result.reasons)
elif not locked:
    if st.button("Start settlement", type="primary"):
        s = Settlement(c.estimate, G)
        ss.settlement = s
        reply = s.opening()
        ss.chat = [{"role": "assistant", "content": reply.text}]
        audit.add("human", "detections_confirmed", {"detections": [vars(d) for d in dets]})
        audit.add("system", "estimate_computed", {"estimate": c.estimate, "floor": s.floor, "ceiling": s.ceiling})
        audit.add("ai", "offer_made", {"amount": reply.offer, "final": reply.final_offer})
        st.rerun()

s: Settlement | None = ss.settlement
if s:
    st.subheader("Settlement chat")
    for msg in ss.chat:
        st.chat_message(msg["role"]).write(msg["content"])

    if s.status == "open":
        text = st.chat_input("Reply with accept, or the amount you expect")
        if text:
            audit.add("customer", "message", {"text": text})
            reply = s.respond(text)
            body = reply.text
            if chat_model and reply.status != "escalated":
                allowed = {str(int(x)) for x in (reply.offer, s.final_amount) if x}
                body = llm.rephrase(chat_model, reply.text, allowed, host)
            ss.chat += [{"role": "user", "content": text}, {"role": "assistant", "content": body}]
            audit.add("ai", "reply", {"status": reply.status, "offer": reply.offer, "final": reply.final_offer})
            if reply.status != "open":
                audit.add("system", reply.status, {"amount": s.final_amount, "reason": s.reason})
                fraud.register(ss.media, ss.claim_id, SEEN)
            st.rerun()
    elif s.status == "accepted":
        st.success(f"Final cash settlement: {inr(s.final_amount)}")
    else:
        show_escalation([s.reason])

with st.expander("Audit trail"):
    st.caption("Hash chain intact" if audit.verify() else "Hash chain BROKEN")
    st.json(audit.entries)
