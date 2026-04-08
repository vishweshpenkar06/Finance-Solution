import asyncio
import json
from typing import Dict, Set, List
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

class ConnectionManager:
    """Manage WebSocket connections for real-time streaming"""
    
    def __init__(self):
        # User ID -> Set of WebSocket connections
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # Portfolio ID -> Set of subscribed connections
        self.portfolio_subscribers: Dict[int, Set[WebSocket]] = {}
        # Symbol -> Set of subscribed connections
        self.symbol_subscribers: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        # Remove from all subscriptions
        for subscribers in self.portfolio_subscribers.values():
            subscribers.discard(websocket)
        for subscribers in self.symbol_subscribers.values():
            subscribers.discard(websocket)
    
    def subscribe_to_portfolio(self, websocket: WebSocket, portfolio_id: int):
        if portfolio_id not in self.portfolio_subscribers:
            self.portfolio_subscribers[portfolio_id] = set()
        self.portfolio_subscribers[portfolio_id].add(websocket)
    
    def subscribe_to_symbol(self, websocket: WebSocket, symbol: str):
        if symbol not in self.symbol_subscribers:
            self.symbol_subscribers[symbol] = set()
        self.symbol_subscribers[symbol].add(websocket)
    
    async def send_to_user(self, user_id: int, message: dict):
        """Send message to all connections for a user"""
        if user_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.add(connection)
            
            # Clean up disconnected
            for conn in disconnected:
                self.active_connections[user_id].discard(conn)
    
    async def send_to_portfolio_subscribers(self, portfolio_id: int, message: dict):
        """Send message to all subscribers of a portfolio"""
        if portfolio_id in self.portfolio_subscribers:
            disconnected = set()
            for connection in self.portfolio_subscribers[portfolio_id]:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.add(connection)
            
            for conn in disconnected:
                self.portfolio_subscribers[portfolio_id].discard(conn)
    
    async def send_to_symbol_subscribers(self, symbol: str, message: dict):
        """Send price update to symbol subscribers"""
        if symbol in self.symbol_subscribers:
            disconnected = set()
            for connection in self.symbol_subscribers[symbol]:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.add(connection)
            
            for conn in disconnected:
                self.symbol_subscribers[symbol].discard(conn)
    
    async def broadcast_alert(self, alert: dict):
        """Broadcast alert to relevant users"""
        user_id = alert.get("user_id")
        if user_id and user_id in self.active_connections:
            await self.send_to_user(user_id, {
                "type": "alert",
                "data": alert,
                "timestamp": datetime.utcnow().isoformat()
            })

# Global connection manager instance
manager = ConnectionManager()
