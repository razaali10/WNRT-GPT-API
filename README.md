# WNTR GPT Simulation API

This API simulates water distribution networks using EPANET models with WNTR. It powers the [Custom GPT Assistant](https://chat.openai.com/g/g-681360112e4c8191b104417a2127b025-wntr-analysis-assistant) for hydraulic analysis.

## 🚀 Features
- EPANET/WNTR hydraulic simulations
- Pipe break / node closure modeling
- Resilience, morphology, economic loss, criticality
- Network visualization (base64 PNG)
- GPT-4 interpretations

## 🧪 Test Locally
```bash
uvicorn main:app --reload
