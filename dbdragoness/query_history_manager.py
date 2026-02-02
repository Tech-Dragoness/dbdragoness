import json
import os
from collections import OrderedDict
from datetime import datetime
import hashlib
import logging
import re

logger = logging.getLogger(__name__)

class QueryHistoryManager:
    """Manages permanent query history storage per database handler with multi-command support"""
    
    def __init__(self, history_file='query_history.json'):
        self.history_file = history_file
        self.history = self._load_history()
        self.session_queries = {}  # {session_id: {handler_name: [queries]}}
        # New: Store individual parsed commands for better autocomplete
        self.parsed_commands = {}  # {handler_name: OrderedDict of individual commands}
    
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
                    
                    # Parse all loaded queries into individual commands
                    self._reindex_all_commands(history)
                    
                    return history
            except Exception as e:
                logger.error(f"Failed to load query history: {e}")
                return {}
        return {}
    
    def _reindex_all_commands(self, history):
        """Parse all historical queries into individual commands"""
        self.parsed_commands = {}
        for handler_name, queries in history.items():
            if handler_name not in self.parsed_commands:
                self.parsed_commands[handler_name] = OrderedDict()
            
            for query in queries.values():
                commands = self._split_query_into_commands(query)
                for cmd in commands:
                    cmd_hash = self._get_query_hash(cmd)
                    if cmd_hash not in self.parsed_commands[handler_name]:
                        self.parsed_commands[handler_name][cmd_hash] = {
                            'command': cmd,
                            'original_query': query,
                            'last_used': datetime.now().isoformat()
                        }
    
    def _split_query_into_commands(self, query):
        """
        Split a multi-line query into individual SQL commands.
        Handles semicolon-separated commands and preserves command integrity.
        """
        if not query or not query.strip():
            return []
        
        # Split by semicolons, but be smart about it
        commands = []
        current_command = []
        in_string = False
        string_char = None
        
        lines = query.split('\n')
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('--'):
                continue
            
            # Process character by character to handle strings properly
            i = 0
            while i < len(line):
                char = line[i]
                
                # Handle string literals
                if char in ('"', "'", '`') and (i == 0 or line[i-1] != '\\'):
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char:
                        in_string = False
                        string_char = None
                
                # Found a semicolon outside of string
                if char == ';' and not in_string:
                    current_command.append(line[:i].strip())
                    
                    # Finalize this command
                    cmd_text = ' '.join(current_command).strip()
                    if cmd_text:
                        commands.append(cmd_text)
                    
                    current_command = []
                    line = line[i+1:]  # Continue with remainder of line
                    i = 0
                    continue
                
                i += 1
            
            # Add remaining part of line to current command
            if line.strip():
                current_command.append(line.strip())
        
        # Don't forget the last command if no semicolon at end
        if current_command:
            cmd_text = ' '.join(current_command).strip()
            if cmd_text:
                commands.append(cmd_text)
        
        return commands
    
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
        """Add query to both permanent and session history, and parse individual commands"""
        query = query.strip()
        if not query:
            return
        
        # Initialize handler in permanent history if needed
        if handler_name not in self.history:
            self.history[handler_name] = OrderedDict()
        
        if handler_name not in self.parsed_commands:
            self.parsed_commands[handler_name] = OrderedDict()
        
        # Add to permanent history (deduplicated)
        query_hash = self._get_query_hash(query)
        if query_hash not in self.history[handler_name]:
            self.history[handler_name][query_hash] = query
            
            # Parse and store individual commands
            commands = self._split_query_into_commands(query)
            for cmd in commands:
                cmd_hash = self._get_query_hash(cmd)
                self.parsed_commands[handler_name][cmd_hash] = {
                    'command': cmd,
                    'original_query': query,
                    'last_used': datetime.now().isoformat()
                }
            
            # Keep only last 1000 unique queries per handler
            if len(self.history[handler_name]) > 1000:
                # Remove oldest 100
                for _ in range(100):
                    self.history[handler_name].popitem(last=False)
            
            # Keep only last 2000 unique commands per handler
            if len(self.parsed_commands[handler_name]) > 2000:
                for _ in range(200):
                    self.parsed_commands[handler_name].popitem(last=False)
            
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
        """
        Get real-time autocomplete suggestions for partial query.
        Now supports matching individual commands within multi-line queries!
        
        IMPORTANT: Extracts only the CURRENT command being typed (after last semicolon)
        to match against individual commands in history.
        
        Returns dict with:
        - suggestions: List of matching complete queries/commands
        - next_words: List of suggested next words (for word-by-word completion)
        """
        if handler_name not in self.history and handler_name not in self.parsed_commands:
            return {'suggestions': [], 'next_words': []}
        
        # Extract the current command being typed (after the last semicolon)
        current_command = self._extract_current_command(partial_query)
        current_lower = current_command.strip().lower()
        
        logger.debug(f"🔍 Autocomplete input: '{partial_query[:100]}'")
        logger.debug(f"🎯 Current command extracted: '{current_command}'")
        
        if not current_lower:
            return {'suggestions': [], 'next_words': []}
        
        suggestions = []
        seen = set()
        
        # PRIORITY 1: Search individual parsed commands (NEW!)
        if handler_name in self.parsed_commands:
            for cmd_data in reversed(list(self.parsed_commands[handler_name].values())):
                cmd = cmd_data['command']
                cmd_lower = cmd.lower()
                
                # Check if command starts with the current command being typed
                if cmd_lower.startswith(current_lower):
                    if cmd not in seen:
                        suggestions.append({
                            'query': cmd,
                            'type': 'command',
                            'source': 'individual'
                        })
                        seen.add(cmd)
                        
                        if len(suggestions) >= limit:
                            break
        
        # PRIORITY 2: Search full queries (if we need more suggestions)
        # Only if current command matches the start of a full query
        if len(suggestions) < limit and handler_name in self.history:
            for query in reversed(list(self.history[handler_name].values())):
                query_lower = query.lower()
                
                # Check if query starts with the current command
                if query_lower.startswith(current_lower):
                    if query not in seen:
                        suggestions.append({
                            'query': query,
                            'type': 'full_query',
                            'source': 'history'
                        })
                        seen.add(query)
                        
                        if len(suggestions) >= limit:
                            break
        
        # Generate next word suggestions based on current command
        next_words = self._get_next_word_suggestions(handler_name, current_lower, limit=3)
        
        logger.debug(f"✅ Found {len(suggestions)} suggestions for current command")
        
        return {
            'suggestions': suggestions,
            'next_words': next_words
        }
    
    def _extract_current_command(self, partial_query):
        """
        Extract the current command being typed from a multi-line query.
        Returns the text after the last semicolon.
        """
        if not partial_query:
            return ""
        
        # Find the last semicolon
        last_semicolon = partial_query.rfind(';')
        
        if last_semicolon == -1:
            # No semicolon found, return the entire query
            return partial_query.strip()
        
        # Return everything after the last semicolon
        current_cmd = partial_query[last_semicolon + 1:].strip()
        return current_cmd
    
    def _get_next_word_suggestions(self, handler_name, current_command_lower, limit=3):
        """
        Predict the next word based on historical queries.
        This helps with word-by-word autocompletion.
        
        Args:
            current_command_lower: The current command being typed (already lowercased)
        """
        if handler_name not in self.parsed_commands:
            return []
        
        if not current_command_lower:
            return []
        
        # Find all commands that start with the current command
        next_words = {}
        
        for cmd_data in self.parsed_commands[handler_name].values():
            cmd = cmd_data['command']
            cmd_lower = cmd.lower()
            
            if cmd_lower.startswith(current_command_lower):
                # Get the next word after the current command
                remainder = cmd[len(current_command_lower):].strip()
                if remainder:
                    # Extract the first word from remainder
                    next_word_match = re.match(r'^(\S+)', remainder)
                    if next_word_match:
                        next_word = next_word_match.group(1)
                        next_words[next_word.lower()] = next_word
        
        # Return most common next words (limited)
        return list(next_words.values())[:limit]
    
    def get_command_statistics(self, handler_name):
        """Get statistics about command usage"""
        if handler_name not in self.parsed_commands:
            return {
                'total_commands': 0,
                'unique_commands': 0,
                'command_types': {}
            }
        
        commands = self.parsed_commands[handler_name]
        command_types = {}
        
        for cmd_data in commands.values():
            cmd = cmd_data['command'].strip().upper()
            # Extract command type (SELECT, INSERT, UPDATE, etc.)
            first_word = cmd.split()[0] if cmd.split() else 'UNKNOWN'
            command_types[first_word] = command_types.get(first_word, 0) + 1
        
        return {
            'total_commands': len(commands),
            'unique_commands': len(set(c['command'].lower() for c in commands.values())),
            'command_types': command_types
        }