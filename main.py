from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import wntr
import tempfile
import pandas as pd
import openai
import matplotlib.pyplot as plt
import os, io, base64, json

app = FastAPI(
    title="WNTR GPT Simulation API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/")
def root():
    return {"status": "API is live", "docs": "/docs"}

# --- 1. SIMULATE FROM TEXT
@app.post("/simulateFromText")
async def simulate_from_text(
    inp_content: str = Form(...),
    simulation_type: str = Form("EPANET"),
    duration: int = Form(24),
    hydraulic_timestep: int = Form(60),
    demand_model: str = Form("PDD"),
    report_status: str = Form("NO")
):
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".inp", delete=False) as f:
        f.write(inp_content)
        path = f.name
    try:
        wn = wntr.network.WaterNetworkModel(path)
        sim = wntr.sim.EpanetSimulator(wn) if simulation_type.upper() == "EPANET" else wntr.sim.WNTRSimulator(wn)
        results = sim.run_sim()
        pressure = results.node["pressure"].mean().to_dict()
        demand = results.node["demand"].mean().to_dict()
        return {"pressure": pressure, "demand": demand}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        os.remove(path)

# --- 2. SIMULATE DISASTER
class DisasterRequest(BaseModel):
    inp_content: str
    failure_element: str
    failure_type: str
    simulation_hours: int

@app.post("/simulateDisaster")
def simulate_disaster(req: DisasterRequest):
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".inp", delete=False) as f:
        f.write(req.inp_content)
        path = f.name
    try:
        wn = wntr.network.WaterNetworkModel(path)
        if req.failure_type == "pipe_break":
            wn = wntr.morph.split_pipe(wn, req.failure_element)
        elif req.failure_type == "node_closure":
            wn.get_node(req.failure_element).is_isolated = True

        sim = wntr.sim.WNTRSimulator(wn)
        results = sim.run_sim()
        pressure = results.node["pressure"].mean().to_dict()
        demand = results.node["demand"].mean().to_dict()
        return {"pressure": pressure, "demand": demand}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        os.remove(path)

# --- 3. SIMULATE WATER QUALITY
class WaterQualityRequest(BaseModel):
    inp_content: str
    quality_type: str
    trace_node: str = None
    duration: int = 24

@app.post("/simulateWaterQuality")
def simulate_water_quality(req: WaterQualityRequest):
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".inp", delete=False) as f:
        f.write(req.inp_content)
        path = f.name
    try:
        wn = wntr.network.WaterNetworkModel(path)
        wn.options.quality.mode = req.quality_type
        if req.quality_type == "trace" and req.trace_node:
            wn.options.quality.trace_node = req.trace_node
        sim = wntr.sim.EpanetSimulator(wn)
        results = sim.run_sim()
        return {
            "quality_type": req.quality_type,
            "result": results.node["quality"].mean().to_dict()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        os.remove(path)

# --- 4. ANALYZE
class AnalyzeRequest(BaseModel):
    analysis_type: str
    simulation_results: dict

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    try:
        if req.analysis_type == "Resilience":
            avg_pressure = pd.DataFrame(req.simulation_results["pressure"].items())[1].mean()
            avg_demand = pd.DataFrame(req.simulation_results["demand"].items())[1].mean()
            resilience_index = round((avg_pressure / 50) * (avg_demand / 1.0), 3)
            return {"result": f"Estimated resilience index: {resilience_index}"}
        elif req.analysis_type == "Morphology":
            node_count = len(req.simulation_results["pressure"])
            return {"result": f"The network has {node_count} active nodes."}
        else:
            return JSONResponse(status_code=400, content={"error": "Unknown analysis type"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# --- 5. ECONOMIC LOSS
class EconomicLossRequest(BaseModel):
    inp_content: str
    duration: int = 24

@app.post("/economicLoss")
def economic_loss(req: EconomicLossRequest):
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".inp", delete=False) as f:
        f.write(req.inp_content)
        path = f.name
    try:
        wn = wntr.network.WaterNetworkModel(path)
        sim = wntr.sim.WNTRSimulator(wn)
        results = sim.run_sim()
        node_demand = results.node["demand"].mean()
        loss_by_node = (1.0 - node_demand / node_demand.max()) * 100
        total_loss = loss_by_node.sum()
        return {
            "total_loss": round(total_loss, 2),
            "loss_by_node": loss_by_node.to_dict()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        os.remove(path)

# --- 6. CRITICALITY
class CriticalityRequest(BaseModel):
    inp_content: str
    scenario_type: str = "single_pipe"

@app.post("/criticality")
def criticality(req: CriticalityRequest):
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".inp", delete=False) as f:
        f.write(req.inp_content)
        path = f.name
    try:
        wn = wntr.network.WaterNetworkModel(path)
        results = {}
        for pipe in wn.pipe_name_list[:5]:  # limit for speed
            wn_temp = wntr.network.WaterNetworkModel(path)
            wn_temp.get_link(pipe).status = "CLOSED"
            sim = wntr.sim.WNTRSimulator(wn_temp)
            res = sim.run_sim()
            demand = res.node["demand"].mean().sum()
            results[pipe] = round(demand, 3)
        return {"pipe_demand_shortage": results}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        os.remove(path)

# --- 7. PLOT NETWORK
@app.post("/plotNetwork")
async def plot_network(inp_content: str = Form(...)):
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".inp", delete=False) as f:
        f.write(inp_content)
        path = f.name
    try:
        wn = wntr.network.WaterNetworkModel(path)
        fig = plt.figure()
        wn.draw_network()
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode("utf-8")
        return {"image_base64": encoded}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        os.remove(path)

# --- 8. GPT ASK
class AskRequest(BaseModel):
    user_question: str
    pressure_summary: str
    demand_summary: str

@app.post("/ask")
def ask(req: AskRequest):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a hydraulic network expert."},
                {"role": "user", "content": f"{req.user_question}\n\nPressure Summary:\n{req.pressure_summary}\n\nDemand Summary:\n{req.demand_summary}"}
            ]
        )
        return {"answer": response.choices[0].message["content"]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})



       


