"""Plotly visualization generators for API responses."""

import json
from typing import Dict, List, Optional, Any

import polars as pl
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder


def create_presence_bar_chart(df: pl.DataFrame) -> Dict[str, Any]:
    """
    Create a bar chart showing presence completeness per column.
    Returns Plotly figure as JSON.
    """
    presence_cols = [
        "presence SLC",
        "presence GRD",
        "presence OCN",
        "presence L1B XSP A21",
        "presence L1C XSP B17",
    ]
    
    labels = []
    values = []
    colors = []
    
    for col in presence_cols:
        if col in df.columns:
            total = df.height
            present = df.filter(pl.col(col).is_not_null()).height
            pct = (present / total * 100) if total > 0 else 0.0
            labels.append(col.replace("presence ", ""))
            values.append(pct)
            if pct >= 80:
                colors.append("#28a745")
            elif pct >= 50:
                colors.append("#ffc107")
            elif pct > 0:
                colors.append("#dc3545")
            else:
                colors.append("#6c757d")
    
    fig = go.Figure(data=[
        go.Bar(
            x=labels,
            y=values,
            marker_color=colors,
            text=[f"{v:.1f}%" for v in values],
            textposition="outside",
        )
    ])
    
    fig.update_layout(
        title="Presence Completeness",
        yaxis_title="Percentage",
        yaxis=dict(range=[0, 105]),
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    
    return json.loads(json.dumps(fig, cls=PlotlyJSONEncoder))


def create_dataset_completeness_table(
    datasets_data: Dict[str, Dict[str, float]],
    overall: Dict[str, float]
) -> Dict[str, Any]:
    """
    Create an interactive dataset completeness table using Plotly.
    """
    headers = ["Dataset", "SLC", "GRD", "OCN", "L1B A21", "L1C B17", "Overall"]
    
    rows = []
    
    for dataset, metrics in sorted(datasets_data.items()):
        row = [dataset]
        row.append(f"{metrics.get('presence SLC', 0):.1f}%")
        row.append(f"{metrics.get('presence GRD', 0):.1f}%")
        row.append(f"{metrics.get('presence OCN', 0):.1f}%")
        row.append(f"{metrics.get('presence L1B XSP A21', 0):.1f}%")
        row.append(f"{metrics.get('presence L1C XSP B17', 0):.1f}%")
        row.append(f"{metrics.get('overall', 0):.1f}%")
        rows.append(row)
    
    # Add overall row
    overall_row = ["**Overall**"]
    overall_row.append(f"{overall.get('presence SLC', 0):.1f}%")
    overall_row.append(f"{overall.get('presence GRD', 0):.1f}%")
    overall_row.append(f"{overall.get('presence OCN', 0):.1f}%")
    overall_row.append(f"{overall.get('presence L1B XSP A21', 0):.1f}%")
    overall_row.append(f"{overall.get('presence L1C XSP B17', 0):.1f}%")
    overall_row.append(f"{overall.get('overall', 0):.1f}%")
    rows.append(overall_row)
    
    fig = go.Figure(data=[
        go.Table(
            header=dict(
                values=headers,
                fill_color="#2c3e50",
                font=dict(color="white", size=12),
                align="center",
            ),
            cells=dict(
                values=[list(col) for col in zip(*rows)],
                fill_color=[["#f8f9fa", "white"] * len(rows)],
                align=["left"] + ["center"] * (len(headers) - 1),
                font=dict(size=11),
                height=25,
            ),
        )
    ])
    
    fig.update_layout(
        title="Dataset Completeness",
        height=400 + len(rows) * 30,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    
    return json.loads(json.dumps(fig, cls=PlotlyJSONEncoder))