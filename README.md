# 💧 WNTR-GPT API

A FastAPI-based API for simulating water distribution networks using EPANET/WNTR, designed to work with OpenAI Custom GPT Actions.

## 🚀 Features

- Hydraulic & quality simulation from .inp files
- Disaster/failure modeling
- Resilience and criticality analysis
- Economic loss estimation
- Plotting network structure
- GPT-4 summaries and insights

## 🛠 Usage

- Run locally: `uvicorn main:app --reload`
- Deploy with Docker or Render (see `render.yaml`)
- Connect with GPT using `openapi.yaml`

See `docs/` for GPT setup and test prompts.
