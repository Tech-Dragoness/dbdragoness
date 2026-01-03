import logging
from venv import logger
from sqlalchemy.sql import text
from .db_handler import DBHandler
from .db_registry import DBRegistry

class SQLHandler(DBHandler):
    def __init__(self, handler_name=None):
        self.handler_name = handler_name
        self.handler = None
        self._load_handler()
    
    def _load_handler(self):
        handlers = DBRegistry.get_sql_handlers()
        if not handlers:
            raise ValueError("No SQL handlers discovered. Add a *_handler.py file.")
        
        # Use provided name, else first available
        name = self.handler_name or next(iter(handlers))
        if name in handlers:
            self.handler = handlers[name]()
        else:
            raise ValueError(f"SQL handler '{name}' not found. Available: {list(handlers.keys())}")
        
    def _get_connection(self):
        """Return a connection that works with 'with' and .connect()"""
        engine = self.handler.engine
        
        if engine is None:
            raise Exception("No database engine available")
        
        # If handler has a .connect() method (DuckDB does now!), use it
        if hasattr(self.handler, 'connect') and callable(getattr(self.handler, 'connect')):
            return self.handler.connect()
        
        # Otherwise, fall back to SQLAlchemy's engine.connect()
        elif hasattr(engine, 'connect'):
            return engine.connect()
        
        # Fallback: return engine directly (should not happen)
        else:
            return engine
        
    def get_connection_info(self, db_name):
        return self.handler.get_connection_info(db_name)
        
    def _execute(self, query, params=None):
        """Execute query safely across SQLAlchemy and DuckDB"""
        conn = self._get_connection()
    
        # If using SQLAlchemy (has .connect), use text() for param binding
        if hasattr(self.handler.engine, 'connect'):
            if params is not None:
                result = conn.execute(text(query), params)
            else:
                result = conn.execute(text(query))
            # Don't commit here for SELECT queries - let caller handle it
            if not query.strip().upper().startswith('SELECT'):
                conn.commit()
            return result
        else:
            # DuckDB: use raw string + list/tuple params
            if params is not None:
                result = conn.execute(query, params)
            else:
                result = conn.execute(query)
            return result
    
    def create_db(self, db_name):
        self.handler.create_db(db_name)

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
        self.handler.insert(table_name, data)

    def update(self, table_name, data, condition):
        self.handler.update(table_name, data, condition)

    def delete(self, table_name, condition):
        self.handler.delete(table_name, condition)

    def delete_table(self, table_name):
        self.handler.delete_table(table_name)

    def can_convert_column(self, table_name, column, new_type):
        return self.handler.can_convert_column(table_name, column, new_type)

    def modify_table(self, old_table_name, new_table_name, new_columns):
        self.handler.modify_table(old_table_name, new_table_name, new_columns)
        
    def supports_non_pk_autoincrement(self):
        return self.handler.supports_non_pk_autoincrement  

    @property
    def current_db(self):
        return self.handler.current_db

    @current_db.setter
    def current_db(self, value):
        self.handler.current_db = value

    @property
    def engine(self):
        return self.handler.engine

    @engine.setter
    def engine(self, value):
        self.handler.engine = value
        
    def supports_joins(self):
        return self.handler.supports_joins()

    def supports_triggers(self):
        return self.handler.supports_triggers()

    def supports_plsql(self):
        return self.handler.supports_plsql()

    def execute_join(self, join_query):
        return self.handler.execute_join(join_query)

    def create_trigger(self, trigger_name, table_name, trigger_timing, trigger_event, trigger_body):
        logging.debug(f"SQLHandler: Forwarding create_trigger with table_name={table_name}")
        return self.handler.create_trigger(trigger_name, table_name, trigger_timing, trigger_event, trigger_body)

    def list_triggers(self, table_name=None):
        return self.handler.list_triggers(table_name)

    def get_trigger_details(self, trigger_name):
        return self.handler.get_trigger_details(trigger_name)

    def delete_trigger(self, trigger_name, table_name=None):
        logging.debug(f"SQLHandler: Forwarding delete_trigger with table_name={table_name}")
        return self.handler.delete_trigger(trigger_name, table_name=table_name)
    
    def supports_aggregation(self):
        """Return True if database supports aggregation (GROUP BY, SUM, AVG, etc.)"""
        return self.handler.supports_aggregation()
    
    def supports_procedures(self):
        """Check if handler supports stored procedures"""
        if hasattr(self.handler, 'supports_procedures'):
            return self.handler.supports_procedures()
        return False
    
    def get_procedure_call_syntax(self):
        """Return the SQL syntax to call this type of object"""
        return self.handler.get_procedure_call_syntax()

    def execute_procedure(self, procedure_code):
        """Execute stored procedure code"""
        if hasattr(self.handler, 'execute_procedure'):
            return self.handler.execute_procedure(procedure_code)
        raise NotImplementedError(f"{self.handler.DB_NAME} does not support procedures")

    def list_procedures(self):
        """List all stored procedures"""
        if hasattr(self.handler, 'list_procedures'):
            return self.handler.list_procedures()
        return []

    def get_procedure_definition(self, procedure_name):
        """Get procedure definition"""
        if hasattr(self.handler, 'get_procedure_definition'):
            return self.handler.get_procedure_definition(procedure_name)
        return None

    def drop_procedure(self, procedure_name, is_function=False):
        """Drop a stored procedure"""
        if hasattr(self.handler, 'drop_procedure'):
            return self.handler.drop_procedure(procedure_name, is_function)
        raise NotImplementedError(f"{self.handler.DB_NAME} does not support procedures")

    def get_procedure_placeholder_example(self):
        """Get database-specific example for procedures tab"""
        if hasattr(self.handler, 'get_procedure_placeholder_example'):
            return self.handler.get_procedure_placeholder_example()
        return "This database does not support stored procedures."
    
    def supports_user_management(self):
        """Check if handler supports user management"""
        if hasattr(self.handler, 'supports_user_management'):
            return self.handler.supports_user_management()
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
        return self.handler.execute_plsql(plsql_code)
    
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
        """SQL databases don't use column definitions, but method required for interface compatibility"""
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
    
    def add_check_constraint_to_existing_table(self, table_name, column_name, expression, conn=None):
        """Used for transferring validation rules into check constraints"""
        self.handler.add_check_constraint_to_existing_table(table_name, column_name, expression, conn=None)
        
        
    # === VIEWS SUPPORT ===
    def supports_views(self):
        """Check if database supports views"""
        return self.handler.supports_views()

    def list_views(self):
        """List all views in current database"""
        return self.handler.list_views()

    def create_view(self, view_name, view_query):
        """Create a new view"""
        return self.handler.create_view(view_name, view_query)

    def drop_view(self, view_name):
        """Drop a view"""
        return self.handler.drop_view(view_name)

    def get_view_definition(self, view_name):
        """Get the SQL definition of a view"""
        return self.handler.get_view_definition(view_name)
        
    # === PARTITIONS SUPPORT ===
    def supports_partitions(self):
        """Check if database supports table partitions"""
        return self.handler.supports_partitions()
    
    def supports_partition_listing(self):
        return self.handler.supports_partition_listing()

    def supports_partition_creation(self):
        return self.handler.supports_partition_creation()

    def supports_partition_deletion(self):
        return self.handler.supports_partition_deletion()

    def list_partitions(self, table_name):
        """List all partitions for a table"""
        return self.handler.list_partitions(table_name)

    def create_partition(self, table_name, partition_config):
        """Create a partition on a table"""
        return self.handler.create_partition(table_name, partition_config)

    def drop_partition(self, table_name, partition_name):
        """Drop a partition from a table"""        
        return self.handler.drop_partition(table_name, partition_name)
    
    # === NORMALIZATION SUPPORT ===
    def analyze_for_normalization(self):
        """Analyze database structure for normalization opportunities"""
        return self.handler.analyze_for_normalization()

    def normalize_database(self, normal_form, analysis_data):
        """
        Normalize database to specified normal form.
        This is a simplified implementation - real normalization requires deep analysis.
        """
        return self.handler.normalize_database(normal_form, analysis_data)