import json
import os
from collections import OrderedDict
from datetime import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)

class QueryHistoryManager:
    """Manages permanent query history storage per database handler"""
    
    def __init__(self, history_file='query_history.json'):
        self.history_file = history_file
        self.history = self._load_history()
        self.session_queries = {}  # {session_id: {handler_name: [queries]}}
    
    def _load_history(self):
        """Load query history from JSON file"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert lists back to OrderedDicts with hash keys
                    history = {}
                    for handler, queries in data.items():
                        history[handler] = OrderedDict()
                        for query in queries:
                            query_hash = self._get_query_hash(query)
                            history[handler][query_hash] = query
                    return history
            except Exception as e:
                logger.error(f"Failed to load query history: {e}")
                return {}
        return {}
    
    def _save_history(self):
        """Save query history to JSON file"""
        try:
            # Convert OrderedDicts to lists for JSON serialization
            data = {}
            for handler, queries in self.history.items():
                data[handler] = list(queries.values())
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save query history: {e}")
    
    def _get_query_hash(self, query):
        """Generate hash for query deduplication"""
        return hashlib.md5(query.strip().lower().encode()).hexdigest()
    
    def add_query(self, query, handler_name, session_id):
        """Add query to both permanent and session history"""
        query = query.strip()
        if not query:
            return
        
        # Initialize handler in permanent history if needed
        if handler_name not in self.history:
            self.history[handler_name] = OrderedDict()
        
        # Add to permanent history (deduplicated)
        query_hash = self._get_query_hash(query)
        if query_hash not in self.history[handler_name]:
            self.history[handler_name][query_hash] = query
            
            # Keep only last 1000 unique queries per handler
            if len(self.history[handler_name]) > 1000:
                # Remove oldest 100
                for _ in range(100):
                    self.history[handler_name].popitem(last=False)
            
            # Save to file
            self._save_history()
        
        # Add to session history (NOT deduplicated - keep all executions)
        if session_id not in self.session_queries:
            self.session_queries[session_id] = {}
        
        if handler_name not in self.session_queries[session_id]:
            self.session_queries[session_id][handler_name] = []
        
        # Add to session (keep duplicates, keep order)
        self.session_queries[session_id][handler_name].append(query)
        
        # Keep only last 50 queries per handler per session
        if len(self.session_queries[session_id][handler_name]) > 50:
            self.session_queries[session_id][handler_name] = \
                self.session_queries[session_id][handler_name][-50:]
    
    def get_session_queries(self, session_id, handler_name):
        """Get queries for specific handler in current session ONLY"""
        if session_id not in self.session_queries:
            return []
        
        if handler_name not in self.session_queries[session_id]:
            return []
        
        return self.session_queries[session_id][handler_name]
    
    def get_permanent_queries(self, handler_name, limit=100):
        """Get permanent queries for specific handler (deduplicated)"""
        if handler_name not in self.history:
            return []
        
        queries = list(self.history[handler_name].values())
        return list(reversed(queries[-limit:]))  # Most recent first
    
    def search_queries(self, handler_name, search_term, limit=50):
        """Search permanent queries for specific handler"""
        if handler_name not in self.history:
            return []
        
        search_term = search_term.lower()
        matching = []
        
        for query in reversed(list(self.history[handler_name].values())):
            if search_term in query.lower():
                matching.append(query)
                if len(matching) >= limit:
                    break
        
        return matching
    
    def clear_session(self, session_id):
        """Clear session history"""
        if session_id in self.session_queries:
            del self.session_queries[session_id]
    
    def get_all_handlers(self):
        """Get list of all handlers with history"""
        return list(self.history.keys())
    
    def get_realtime_suggestions(self, handler_name, partial_query, limit=5):
        """Get real-time autocomplete suggestions for partial query"""
        if handler_name not in self.history:
            return []
    
        partial_lower = partial_query.strip().lower()
        if not partial_lower:
            return []
    
        # Find matching queries (prefix match for better autocomplete)
        suggestions = []
        seen = set()  # Prevent duplicates in suggestions
    
        # Search through queries in reverse (most recent first)
        for query in reversed(list(self.history[handler_name].values())):
            query_lower = query.lower()
        
            # Check if query starts with or contains the partial query
            if query_lower.startswith(partial_lower) or partial_lower in query_lower:
                # Avoid duplicate suggestions
                if query not in seen:
                    suggestions.append(query)
                    seen.add(query)
                
                    if len(suggestions) >= limit:
                        break
    
        return suggestions