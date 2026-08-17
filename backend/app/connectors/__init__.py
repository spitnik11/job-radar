"""Connector registry. Adding a source = drop a module here and register it (spec section 8)."""

from .greenhouse import GreenhouseConnector
from .lever import LeverConnector
from .ashby import AshbyConnector

CONNECTORS = {
    c.connector_id: c
    for c in (GreenhouseConnector(), LeverConnector(), AshbyConnector())
}
