#!/usr/bin/env python3
from flask import Flask, jsonify, request
from typing import Dict

from core.logger import get_logger
from core.config import config

class WebInterface:
    def __init__(self):
        self.logger = get_logger('interaction_module.web')
        self.app = Flask(__name__)
        self._setup_routes()
    
    def _setup_routes(self):
        @self.app.route('/api/status')
        def get_status():
            return jsonify({'status': 'running', 'symbol': config.SYMBOL})
        
        @self.app.route('/api/balance')
        def get_balance():
            return jsonify({'balance_btc': config.POSITION_BTC})
        
        @self.app.route('/api/positions')
        def get_positions():
            return jsonify({'positions': []})
    
    def run(self):
        self.logger.info(f"启动Web服务: {config.WEB_HOST}:{config.WEB_PORT}")
        self.app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=False)
