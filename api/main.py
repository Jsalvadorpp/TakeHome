"""FastAPI application for serving hail swath polygons.

This is the main entry point for the API. It initializes the FastAPI app,
sets up CORS middleware, and includes all endpoint routers.

Each router is defined in a separate file in api/routers/ for better organization
and scalability.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import health, swaths

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="MRMS Hail Swaths API")

# Configure CORS to allow web viewer to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (each router file handles a specific domain)
app.include_router(health.router, tags=["health"])
app.include_router(swaths.router, tags=["swaths"])
