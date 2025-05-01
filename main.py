from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import tempfile
import wntr
import pandas as pd
import openai
import os
import io
import matplotlib.pyplot as plt
import base64

app = FastAPI(title="WNTR GPT Simulation API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

openai.api_key = os.getenv("OPENAI_API_KEY")

@app.get("/")
def read_root():
    return {"message": "WNTR GPT API is live."}

@app.post("/simulateFromText")
async def simulate_from_text(
    inp_content: str = Form(...),
    simulation_type: str = Form("EPANET"),
    duration: int = Form(24),
    hydraulic_timestep: int = Form(60),
    demand_model: str = Form("PDD"),
    report_status: str = Form("YES")
):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".inp", mode="w") as temp:
            temp.write(inp_content)
            inp_path = temp.name

        wn = wntr.network.WaterNetworkModel(inp_path)
        wn.options.time.duration = duration * 3600
        wn.options.time.hydraulic_timestep = hydraulic_timestep * 60
        wn.options.hydraulic.demand_model = demand_model
        wn.options.report.status = report_status

        sim = wntr.sim.EpanetSimulator(wn) if simulation_type == "EPANET" else wntr.sim.WNTRSimulator(wn)
        results = sim.run_sim()

        return {
            "pressure": results.node["pressure"].to_dict(),
            "demand": results.node["demand"].to_dict()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

class DisasterScenarioRequest(BaseModel):
    inp_content: str
    failure_element: str
    failure_type: str
    simulation_hours: int

@app.post("/simulateDisaster")
async def simulate_disaster(request: DisasterScenarioRequest):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".inp", mode="w") as temp:
            temp.write(request.inp_content)
            inp_path = temp.name

        wn = wntr.network.WaterNetworkModel(inp_path)

        if request.failure_type == "pipe_break":
            wn.close_link(request.failure_element)
        elif request.failure_type == "node_closure":
            wn.remove_node(request.failure_element)

        wn.options.time.duration = request.simulation_hours * 3600
        sim = wntr.sim.WNTRSimulator(wn)
        results = sim.run_sim()

        return {
            "failure_type": request.failure_type,
            "element": request.failure_element,
            "pressure": results.node["pressure"].to_dict(),
            "demand": results.node["demand"].to_dict()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


class QualityRequest(BaseModel):
    inp_content: str
    quality_type: str
    trace_node: str = None
    duration: int = 24

@app.post("/simulateWaterQuality")
def simulate_water_quality(request: QualityRequest):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".inp", mode="w") as temp:
            temp.write(request.inp_content)
            inp_path = temp.name

        wn = wntr.network.WaterNetworkModel(inp_path)
        wn.options.time.duration = request.duration * 3600

        if request.quality_type == "age":
            wn.options.quality.mode = 'AGE'
        elif request.quality_type == "trace" and request.trace_node:
            wn.options.quality.mode = 'TRACE'
            wn.options.quality.trace_node = request.trace_node

        sim = wntr.sim.EpanetSimulator(wn)
        results = sim.run_sim()

        return {
            "quality_type": request.quality_type,
            "result": results.node["quality"].to_dict()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

class AnalysisRequest(BaseModel):
    analysis_type: str
    simulation_results: dict

@app.post("/analyze")
def run_advanced_analysis(request: AnalysisRequest):
    try:
        pressure_df = pd.DataFrame(request.simulation_results.get("pressure", {}))
        if request.analysis_type == "Resilience":
            result = wntr.metrics.resilience.reliability(pressure_df)
            return {"result": round(result, 4)}
        elif request.analysis_type == "Morphology":
            return {"num_nodes": pressure_df.shape[0], "num_timesteps": pressure_df.shape[1]}
        else:
            return {"result": "Unsupported analysis type"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


class EconomicLossRequest(BaseModel):
    inp_content: str
    duration: int = 24

@app.post("/economicLoss")
def estimate_economic_loss(request: EconomicLossRequest):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".inp", mode="w") as temp:
            temp.write(request.inp_content)
            inp_path = temp.name

        wn = wntr.network.WaterNetworkModel(inp_path)
        wn.options.time.duration = request.duration * 3600
        sim = wntr.sim.WNTRSimulator(wn)
        results = sim.run_sim()

        pop = wntr.metrics.population.estimate_population(wn)
        loss = wntr.metrics.economic_loss.economic_loss(results, pop)

        return {
            "total_loss": round(loss.sum().sum(), 2),
            "loss_by_node": loss.sum().to_dict()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


class CriticalityRequest(BaseModel):
    inp_content: str
    scenario_type: str = "pipe_closure"

@app.post("/criticality")
def run_criticality_analysis(request: CriticalityRequest):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".inp", mode="w") as temp:
            temp.write(request.inp_content)
            inp_path = temp.name

        wn = wntr.network.WaterNetworkModel(inp_path)
        link_names = wn.pipe_name_list
        shortages = {}
        for link in link_names:
            wn_temp = wntr.network.WaterNetworkModel(inp_path)
            wn_temp.close_link(link)
            sim = wntr.sim.WNTRSimulator(wn_temp)
            results = sim.run_sim()
            total_demand = results.node["demand"].sum().sum()
            shortages[link] = total_demand

        return {"pipe_demand_shortage": shortages}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
@app.post("/plotNetwork")
def plot_network(inp_content: str = Form(...)):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".inp", mode="w") as temp:
            temp.write(inp_content)
            inp_path = temp.name

        wn = wntr.network.WaterNetworkModel(inp_path)
        fig = wntr.graphics.plot_network(wn, node_attribute=None, link_attribute=None, title='Network Layout')

        buf = io.BytesIO()
        fig.savefig(buf, format='png')
        plt.close(fig)
        buf.seek(0)

        encoded = base64.b64encode(buf.read()).decode("utf-8")
        return {"image_base64": encoded}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


class GPTRequest(BaseModel):
    user_question: str
    pressure_summary: str
    demand_summary: str

@app.post("/ask")
def ask_gpt_assistant(request: GPTRequest):
    try:
        prompt = f"""
User Question: {request.user_question}

Pressure Summary:
{request.pressure_summary}

Demand Summary:
{request.demand_summary}
"""
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a hydraulic modeling assistant using WNTR and EPANET."},
                {"role": "user", "content": prompt}
            ]
        )
        return {"answer": response["choices"][0]["message"]["content"]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
