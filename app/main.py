from pathlib import Path

import pandas as pd
import streamlit as st

from brain.agents import Brain
from brain.models import Asset, load_persona

ROOT = Path(__file__).resolve().parents[1]
st.set_page_config(page_title="AlphaForge AI", page_icon="◈", layout="wide")


@st.cache_data
def assets():
    return [
        Asset(**row)
        for row in pd.read_csv(ROOT / "data/raw/assets_universe.csv").to_dict("records")
    ]


st.title("AlphaForge AI")
st.caption("Larpathon · Décision d’investissement explicable et gouvernée — prototype de datathon")
name = st.sidebar.selectbox("Persona", ["amira", "mateo", "robert"])
request = st.sidebar.text_area(
    "Demande de l’investisseur", "Construire une allocation diversifiée."
)
p = load_persona(name, ROOT)
d = Brain(assets()).recommend(p, request)
col1, col2, col3 = st.columns(3)
col1.metric("Rendement attendu", f"{d.portfolio.expected_return:.1%}")
col2.metric("Volatilité proxy", f"{d.portfolio.volatility:.1%}")
col3.metric("Max drawdown proxy", f"{d.portfolio.max_drawdown_proxy:.1%}")
st.subheader(f"Recommandation pour {p.name}")
st.info(d.recommendation)
if d.portfolio.refused:
    st.error("Garde-fou anti-sycophance : demande refusée.")
st.subheader("Allocation proposée")
st.dataframe(
    pd.DataFrame([a.model_dump() for a in d.portfolio.allocations]), use_container_width=True
)
st.subheader("Inspecteur de traces")
for e in d.trace:
    with st.expander(f"{e.agent} · {e.action}"):
        st.write(e.reasoning)
        st.caption(" · ".join(e.evidence))
