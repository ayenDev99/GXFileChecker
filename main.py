from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import pandas as pd
import io

app = FastAPI()

@app.post("/compare-csvs/")
async def compare_csvs(file1: UploadFile = File(...), file2: UploadFile = File(...), column: str = "total"):
    try:
        # Read uploaded CSVs into DataFrames
        df1 = pd.read_csv(io.BytesIO(await file1.read()))
        df2 = pd.read_csv(io.BytesIO(await file2.read()))

        # Sum the specified column
        total1 = df1[column].sum()
        total2 = df2[column].sum()

        result = {
            "file1_total": total1,
            "file2_total": total2,
            "match": total1 == total2
        }

        return JSONResponse(content=result)

    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
