from abc import ABC, abstractmethod

class DBHandler(ABC):
    @abstractmethod
    def create_db(self, db_name):
        pass

    @abstractmethod
    def delete_db(self, db_name):
        pass

    @abstractmethod
    def switch_db(self, db_name):
        pass

    @abstractmethod
    def list_dbs(self):
        pass

    @abstractmethod
    def list_tables(self):
        pass

    @abstractmethod
    def list_tables_for_db(self, db_name):
        pass

    @abstractmethod
    def get_supported_types(self):
        pass

    @abstractmethod
    def get_table_schema(self, table_name):
        pass

    @abstractmethod
    def read(self, table_name):
        pass

    @abstractmethod
    def execute_query(self, query):
        pass

    @abstractmethod
    def insert(self, table_name, data):
        pass

    @abstractmethod
    def update(self, table_name, data, condition):
        pass

    @abstractmethod
    def delete(self, table_name, condition):
        pass

    @abstractmethod
    def delete_table(self, table_name):
        pass

    @abstractmethod
    def can_convert_column(self, table_name, column, new_type):
        pass

    @abstractmethod
    def modify_table(self, old_table_name, new_table_name, new_columns):
        pass
    
    @abstractmethod
    def supports_non_pk_autoincrement(self):
        pass  
    
    @abstractmethod
    def supports_joins(self):
        pass

    @abstractmethod
    def supports_triggers(self):
        pass

    @abstractmethod
    def supports_plsql(self):
        pass

    @abstractmethod
    def execute_join(self, join_query):
        pass

    @abstractmethod
    def create_trigger(self, trigger_name, table_name, trigger_timing, trigger_event, trigger_body):
        pass

    @abstractmethod
    def list_triggers(self, table_name=None):
        pass

    @abstractmethod
    def get_trigger_details(self, trigger_name):
        pass

    @abstractmethod
    def delete_trigger(self, trigger_name):
        pass

    @abstractmethod
    def execute_plsql(self, plsql_code):
        pass
    
    @abstractmethod
    def get_connection_info(self, db_name):
        """Return connection string and test code for this database"""
        pass
    
    @abstractmethod
    def supports_aggregation(self):
        """Return True if database supports aggregation (GROUP BY, SUM, AVG, etc.)"""
        return False
    
    @abstractmethod
    def supports_procedures(self):
        """Override in child classes - return True if DB supports stored procedures"""
        return False
    
    @abstractmethod
    def execute_procedure(self, procedure_code):
        """Execute stored procedure/function code - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support stored procedures")
    
    @abstractmethod
    def list_procedures(self):
        """List all stored procedures/functions - override in child classes"""
        return []
    
    @abstractmethod
    def get_procedure_definition(self, procedure_name):
        """Get the source code of a procedure - override in child classes"""
        return None
    
    @abstractmethod
    def drop_procedure(self, procedure_name, is_function=False):
        """Drop a stored procedure/function - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support stored procedures")
    
    @abstractmethod
    def get_procedure_placeholder_example(self):
        """Return database-specific example code for procedures tab"""
        return "This database does not support stored procedures."
    
    @abstractmethod
    def get_credential_status(self):
        """Return whether credentials are required or not"""
        return { }
        
    @abstractmethod
    def clear_credentials(self):
        """Clears stored credentials"""
        pass
    
    @abstractmethod
    def supports_user_management(self):
        """Return True if database supports user management"""
        return False

    @abstractmethod
    def list_users(self):
        """List all database users - override in child classes"""
        return []

    @abstractmethod
    def create_user(self, username, password, privileges):
        """Create a new user - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support user management")

    @abstractmethod
    def update_user(self, username, password, privileges):
        """Update user credentials/privileges - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support user management")

    @abstractmethod
    def delete_user(self, username):
        """Delete a user - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support user management")

    @abstractmethod
    def get_user_privileges(self, username):
        """Get privileges for a specific user - override in child classes"""
        return []

    @abstractmethod
    def get_user_connection_info(self, username):
        """Return connection info for a specific user"""
        return {
            'connection_string': 'User management not supported',
            'test_code': 'User management not supported',
        'notes': []
        }
        
    @abstractmethod
    def build_column_definitions(self, schema, quote=True):
        """Return column schema"""
        return []
    
    @abstractmethod
    def reset_sequence_after_copy(self, table_name, column_name):
        """For Sequence Reset while copying/renaming database"""
        pass  
    
    @abstractmethod
    def get_foreign_keys(self, table_name):
        """Fetch foreign keys"""
        return []

    @abstractmethod
    def create_foreign_key(self, table_name, constraint_name, column_name,
                        foreign_table, foreign_column, on_update, on_delete):
        """Create foreign keys"""
        pass
    
    @abstractmethod
    def get_views(self):
        """Fetch Views"""
        return []

    @abstractmethod
    def create_view(self, view_name, view_definition):
        """Create Views"""
        pass
    
    @abstractmethod
    def copy_table(self, source_table, dest_table):
        """Copy table structure and data - override in child classes for optimization"""
        # Default implementation - handlers can override for better performance
        raise NotImplementedError(f"{self.DB_NAME} must implement copy_table")

    @abstractmethod
    def copy_triggers(self, source_table, dest_table):
        """Copy triggers from source table to destination - override in child classes"""
        # Default: do nothing (not all databases support triggers)
        pass
    
    @abstractmethod
    def get_table_connection_info(self, db_name, table_name):
        """Return table-specific connection information"""
        pass
    
    @abstractmethod
    def supports_check_constraints(self):
        """Return True if database supports CHECK constraints"""
        return False

    @abstractmethod
    def get_check_constraints(self, table_name):
        """Get CHECK constraints for a table"""
        return []

    @abstractmethod
    def validate_check_constraint(self, constraint_expression):
        """Validate a CHECK constraint expression"""
        return True