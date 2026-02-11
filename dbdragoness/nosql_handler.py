# nosql_handler.py
import logging
from venv import logger
from .db_handler import DBHandler
from .db_registry import DBRegistry

class NoSQLHandler(DBHandler):
    def __init__(self, handler_name=None):
        self.handler_name = handler_name
        self.handler = None
        self.logger = logging.getLogger(__name__)  # ← ADD THIS
        self.handlers = DBRegistry.get_nosql_handlers()
        self._load_handler()
    
    def _load_handler(self):
        handlers = DBRegistry.get_nosql_handlers()
        if not handlers:
            raise ValueError("No NoSQL handlers discovered. Add a *_handler.py file.")
        
        name = self.handler_name or next(iter(handlers))
        if name in handlers:
            self.handler = handlers[name]()
        else:
            raise ValueError(f"NoSQL handler '{name}' not found. Available: {list(handlers.keys())}")
        
    def get_connection_info(self, db_name):
        return self.handler.get_connection_info(db_name)
        
    def _close_current(self):
        """Close current handler's DB if it has a close method"""
        if self.handler and hasattr(self.handler, 'close_db'):
            try:
                self.handler.close_db()
                self.logger.debug(f"Auto-closed {self.handler.DB_NAME} connection")
            except Exception as e:
                self.logger.warning(f"Error closing {self.handler.DB_NAME}: {e}")
        
    def switch_handler(self, name):
        if name not in self.handlers:
            raise ValueError(f"NoSQL handler '{name}' not found")
        self._close_current()
        self.handler = self.handlers[name]()
        self.current_handler = name
        self.logger.debug(f"Switched to NoSQL handler: {name}")
        
    def count_documents(self, table_name):
        if hasattr(self.handler, 'count_documents'):
            return self.handler.count_documents(table_name)
        else:
            # Fallback for handlers without count_documents
            docs = self.handler.read(table_name)
            return len(docs) if docs else 0
    
    def create_db(self, db_name):
        self.handler.create_db(db_name)
        
    def close_db(self):
        """Close the underlying handler's database connection"""
        if hasattr(self.handler, 'close_db'):
            self.handler.close_db()

    def delete_db(self, db_name):
        self.handler.delete_db(db_name)

    def switch_db(self, db_name):
        self.handler.switch_db(db_name)

    def list_dbs(self):
        return self.handler.list_dbs()

    def list_tables(self):
        return self.handler.list_tables()

    def list_tables_for_db(self, db_name):
        return self.handler.list_tables_for_db(db_name)

    def get_supported_types(self):
        return self.handler.get_supported_types()

    def get_table_schema(self, table_name):
        return self.handler.get_table_schema(table_name)

    def read(self, table_name):
        return self.handler.read(table_name)

    def execute_query(self, query):
        return self.handler.execute_query(query)

    def insert(self, table_name, data):
        return self.handler.insert(table_name, data)

    def update(self, table_name, doc_id, data):
        self.handler.update(table_name, doc_id, data)

    def delete(self, table_name, doc_id):
        self.handler.delete(table_name, doc_id)

    def delete_table(self, table_name):
        self.handler.delete_table(table_name)

    def can_convert_column(self, table_name, column, new_type):
        return self.handler.can_convert_column(table_name, column, new_type)

    def modify_table(self, old_table_name, new_table_name, new_columns):
        self.handler.modify_table(old_table_name, new_table_name, new_columns)
        
    def supports_non_pk_autoincrement(self):
        return self.handler.supports_non_pk_autoincrement

    def get_document(self, table_name, doc_id):
        return self.handler.get_document(table_name, doc_id)

    def create_collection(self, collection_name):
        self.handler.create_collection(collection_name)

    def get_all_keys(self, collection_name):
        return self.handler.get_all_keys(collection_name)
    
    def get_primary_key_name(self):
        """Return the primary key field name for this NoSQL database"""
        if hasattr(self.handler, 'get_primary_key_name'):
            return self.handler.get_primary_key_name()
        return '_id'  # Default fallback

    @property
    def current_db(self):
        return self.handler.current_db

    @current_db.setter
    def current_db(self, value):
        self.handler.current_db = value

    @property
    def db(self):
        return self.handler.db

    @db.setter
    def db(self, value):
        self.handler.db = value
        
    def supports_joins(self):
        return getattr(self.handler, 'supports_joins', lambda: False)()

    def supports_triggers(self):
        return getattr(self.handler, 'supports_triggers', lambda: False)()

    def supports_plsql(self):
        return False

    def execute_join(self, join_query):
        if hasattr(self.handler, 'execute_join'):
            return self.handler.execute_join(join_query)
        raise NotImplementedError("Joins not supported in this NoSQL database")

    def create_trigger(self, trigger_name, table_name, trigger_timing, trigger_event, trigger_body):
        if hasattr(self.handler, 'create_trigger'):
            return self.handler.create_trigger(trigger_name, table_name, trigger_timing, trigger_event, trigger_body)
        raise NotImplementedError("Triggers not supported in NoSQL")

    def list_triggers(self, table_name=None):
        if hasattr(self.handler, 'list_triggers'):
            return self.handler.list_triggers(table_name)
        return []

    def get_trigger_details(self, trigger_name):
        if hasattr(self.handler, 'get_trigger_details'):
            return self.handler.get_trigger_details(trigger_name)
        raise NotImplementedError("Triggers not supported in NoSQL")

    def delete_trigger(self, trigger_name):
        if hasattr(self.handler, 'delete_trigger'):
            return self.handler.delete_trigger(trigger_name)
        raise NotImplementedError("Triggers not supported in NoSQL")
    
    def supports_aggregation(self):
        """Return True if database supports aggregation (GROUP BY, SUM, AVG, etc.)"""
        return self.handler.supports_aggregation()
    
    def supports_aggregation_pipeline(self):
        """Return True if database supports aggregation pipelines"""
        if hasattr(self.handler, 'supports_aggregation_pipeline'):
            return self.handler.supports_aggregation_pipeline()
        raise NotImplementedError("Aggregation pipelines not supported in this handler") 
    
    def supports_procedures(self):
        """Override in child classes - return True if DB supports stored procedures"""
        return False
    
    def get_procedure_call_syntax(self):
        """Return the SQL syntax to call this type of object"""
        return self.handler.get_procedure_call_syntax()
    
    def execute_procedure(self, procedure_code):
        """Execute stored procedure/function code - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support stored procedures")
    
    def list_procedures(self):
        """List all stored procedures/functions - override in child classes"""
        return []
    
    def get_procedure_definition(self, procedure_name):
        """Get the source code of a procedure - override in child classes"""
        return None
    
    def drop_procedure(self, procedure_name, is_function=False):
        """Drop a stored procedure/function - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support stored procedures")
    
    def get_procedure_placeholder_example(self):
        """Return database-specific example code for procedures tab"""
        return "This database does not support stored procedures."
    
    def supports_user_management(self):
        """Check if handler supports user management"""
        if hasattr(self.handler, 'supports_user_management'):
            return self.handler.supports_user_management()
        return False
    
    def requires_credentials(self):
        """Check if handler requires credentials"""
        if hasattr(self.handler, 'requires_credentials'):
            return self.handler.requires_credentials()
        return False

    def list_users(self):
        """List all database users"""
        if hasattr(self.handler, 'list_users'):
            return self.handler.list_users()
        return []

    def create_user(self, username, password, privileges):
        """Create a new user"""
        if hasattr(self.handler, 'create_user'):
            return self.handler.create_user(username, password, privileges)
        raise NotImplementedError(f"{self.handler.DB_NAME} does not support user management")

    def update_user(self, username, password, privileges):
        """Update user credentials/privileges"""
        if hasattr(self.handler, 'update_user'):
            return self.handler.update_user(username, password, privileges)
        raise NotImplementedError(f"{self.handler.DB_NAME} does not support user management")

    def delete_user(self, username):
        """Delete a user"""
        if hasattr(self.handler, 'delete_user'):
            return self.handler.delete_user(username)
        raise NotImplementedError(f"{self.handler.DB_NAME} does not support user management")

    def get_user_privileges(self, username):
        """Get privileges for a specific user"""
        if hasattr(self.handler, 'get_user_privileges'):
            return self.handler.get_user_privileges(username)
        return []

    def get_user_connection_info(self, username):
        """Get connection info for specific user"""
        if hasattr(self.handler, 'get_user_connection_info'):
            return self.handler.get_user_connection_info(username)
        return {
            'connection_string': 'User management not supported',
            'test_code': 'User management not supported',
            'notes': []
        }

    def execute_plsql(self, plsql_code):
        raise NotImplementedError("PL/SQL not supported in NoSQL")
    
    def get_credential_status(self):
        """Return whether credentials are required or not"""
        return self.handler.get_credential_status()
    
    def clear_credentials(self):
        """Clear stored credentials from keyring"""
        if hasattr(self.handler, 'clear_credentials'):
            self.handler.clear_credentials()
        else:
            try:
                import keyring
                handler_name = self.handler.DB_NAME if hasattr(self.handler, 'DB_NAME') else 'unknown'
                keyring.delete_password("dbdragoness", f"{handler_name}_username")
                keyring.delete_password("dbdragoness", f"{handler_name}_password")
                logger.info(f"Cleared credentials for {handler_name}")
            except Exception as e:
                logger.error(f"Failed to clear credentials: {e}")
                raise
            
    def build_column_definitions(self, schema, quote=True):
        """NoSQL databases don't use column definitions, but method required for interface compatibility"""
        self.handler.build_column_definitions(schema, quote=True)
        
    def reset_sequence_after_copy(self, table_name, column_name):
        """For Sequence Reset while copying/renaming database"""
        self.handler.reset_sequence_after_copy(table_name, column_name)  
        
    def get_foreign_keys(self, table_name):
        """Fetch foreign keys"""
        self.handler.get_foreign_keys(table_name) 

    def create_foreign_key(self, table_name, constraint_name, column_name, foreign_table, foreign_column, on_update, on_delete):
        """Create foreign keys"""
        self.handler.create_foreign_key(table_name, constraint_name, column_name, foreign_table, foreign_column, on_update, on_delete) 
        
    def get_views(self):
        """Fetch Views"""
        self.handler.get_views() 

    def create_view(self, view_name, view_definition):
        """Create Views"""
        self.handler.create_view(view_name, view_definition) 
        
    def copy_table(self, source_table, dest_table):
        """Copy table structure and data - override in child classes for optimization"""
        # Default implementation - handlers can override for better performance
        self.handler.copy_table(source_table, dest_table)

    def copy_triggers(self, source_table, dest_table):
        """Copy triggers from source table to destination - override in child classes"""
        # Default: do nothing (not all databases support triggers)
        self.handler.copy_triggers(source_table, dest_table)
        
    def get_table_connection_info(self, db_name, table_name):
        """Return table-specific connection information"""
        return self.handler.get_table_connection_info(db_name, table_name)
    
    def supports_check_constraints(self):
        """Return True if database supports CHECK constraints"""
        return self.handler.supports_check_constraints()

    def get_check_constraints(self, table_name):
        """Get CHECK constraints for a table"""
        return self.handler.get_check_constraints(table_name)

    def validate_check_constraint(self, constraint_expression):
        """Validate a CHECK constraint expression"""
        return self.handler.validate_check_constraint(constraint_expression)
    
    def apply_validation_rules(self, collection_name, validation_rules):
        """
        Apply or update JSON Schema validation on a MongoDB collection.
        validation_rules: dict {field_name: "constraint expression string"}
        """
        self.handler.apply_validation_rules(collection_name, validation_rules)