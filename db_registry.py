import os
import logging
import importlib
import inspect
from pathlib import Path
from .db_handler import DBHandler

class DBRegistry:
    _sql_handlers = {}
    _nosql_handlers = {}
    
    @classmethod
    def discover_handlers(cls):
        """Automatically discover all handler classes in the package"""
        cls._sql_handlers.clear()
        cls._nosql_handlers.clear()
        
        package_dir = Path(__file__).resolve().parent
        logging.debug(f"[DBRegistry] Scanning directory: {package_dir}")
        
        # Scan all Python files in the package
        for file_path in package_dir.glob("*_handler.py"):
            filename = file_path.name
            logging.debug(f"[DBRegistry] Found file: {filename}")
            if filename in ['db_handler.py', 'sql_handler.py', 'nosql_handler.py', 'db_registry.py']:
                continue
            
            module_name = file_path.stem  # Remove .py
            try:
                logging.debug(f"[DBRegistry] Importing module: {module_name}")
                module = importlib.import_module(f'.{module_name}', package='dbdragoness')
                logging.debug(f"[DBRegistry] Successfully imported: {module_name}")
                
                # Find all classes that inherit from DBHandler
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, DBHandler) and obj != DBHandler:
                        # Determine if SQL or NoSQL based on metadata
                        db_type = getattr(obj, 'DB_TYPE', None)
                        db_name = getattr(obj, 'DB_NAME', name.replace('Handler', ''))
                        logging.debug(f"[DBRegistry] Found handler: {db_name} ({db_type})")
                        
                        if db_type == 'sql':
                            cls._sql_handlers[db_name] = obj
                        elif db_type == 'nosql':
                            cls._nosql_handlers[db_name] = obj
                            
            except Exception as e:
                print(f"Failed to load {module_name}: {e}")
                logging.error(f"[DBRegistry] FAILED to load {module_name}: {e}", exc_info=True)
    
    @classmethod
    def get_sql_handlers(cls):
        if not cls._sql_handlers:
            cls.discover_handlers()
        return cls._sql_handlers
    
    @classmethod
    def get_nosql_handlers(cls):
        if not cls._nosql_handlers:
            cls.discover_handlers()
        return cls._nosql_handlers
    
    @classmethod
    def get_handler(cls, db_type, db_name):
        """Get a specific handler instance"""
        if db_type == 'sql':
            handler_class = cls.get_sql_handlers().get(db_name)
        else:
            handler_class = cls.get_nosql_handlers().get(db_name)
        
        if handler_class:
            return handler_class()
        return None