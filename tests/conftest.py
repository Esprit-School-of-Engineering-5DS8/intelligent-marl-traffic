import os

# libsumo runs the simulation in-process; tests start and close one simulation at a time.
os.environ.setdefault("LIBSUMO_AS_TRACI", "1")
