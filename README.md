# Larpathon — AlphaForge AI

Monolithe de décision d'investissement explicable pour le Datathon PolyFinances 2026.

## Architecture

- `app/` : interface Streamlit et façade applicative.
- `brain/` : moteur de décision agentique, modèles métier, métriques quantitatives et garde-fous.
- `data/` : univers d'actifs et profils de personas.
- `tests/` : tests unitaires et d'intégration légère.

Le brain est importé directement par l'app dans cette première version monolithique. La frontière `brain/` est volontairement autonome pour permettre une extraction future vers FastAPI/ECS/Lambda.

## Démarrage rapide

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/main.py
```

Sans dépendances externes, le moteur peut être exercé avec :

```bash
python -m brain.cli --persona amira
pytest
```

## Principes de sécurité

Ce projet est un prototype de datathon et ne constitue pas un conseil financier. Les décisions doivent rester explicables, traçables et soumises à validation humaine. Le `GovernanceAgent` peut refuser une demande incompatible avec le profil, l'horizon ou la capacité de perte.
