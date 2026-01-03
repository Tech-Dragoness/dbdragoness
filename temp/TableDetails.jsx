import React, { useState, useEffect, useRef } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import axios from "axios";
import ChartCreator from "../components/ChartCreator";
import Sidebar from "../components/Sidebar";
import InsertRowModal from "../components/InsertRowModal";
import UpdateRowsModal from "../components/UpdateRowsModal";
import DeleteRowsModal from "../components/DeleteRowsModal";
import EditProcedureModal from "../components/EditProcedureModal";
import EditTriggerModal from "../components/EditTriggerModal";
import { useQueryHistory } from "../hooks/useQueryHistory";
import { useAutocomplete } from "../hooks/useAutocomplete";
import ImportExportTab from "../components/ImportExportTab";

function TableDetails() {
  const { dbName, tableName } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // State management
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [tab, setTab] = useState(searchParams.get("tab") || "data");

  // Data state
  const [columns, setColumns] = useState([]);
  const [rows, setRows] = useState([]);
  const [recordCount, setRecordCount] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [sortColumn, setSortColumn] = useState("");
  const [sortOrder, setSortOrder] = useState("asc");

  // Query state
  const [queryText, setQueryText] = useState("");
  const [queryResult, setQueryResult] = useState(null);
  const { sessionQueries, addQuery, navigateHistory, resetNavigation } =
    useQueryHistory("table");

  // Modal state
  const [showInsertModal, setShowInsertModal] = useState(false);
  const [showUpdateModal, setShowUpdateModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  // Insert/Update state
  const [formData, setFormData] = useState({});
  const [updateFormData, setUpdateFormData] = useState({});
  const [updateCondition, setUpdateCondition] = useState("");
  const [deleteCondition, setDeleteCondition] = useState("");
  const [editingRowId, setEditingRowId] = useState(null);

  // Search/Filter state
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedFields, setSelectedFields] = useState(new Set());
  const [showFilterMenu, setShowFilterMenu] = useState(false);
  const [allRows, setAllRows] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchTimeout, setSearchTimeout] = useState(null);

  // Structure state
  const [types, setTypes] = useState([]);
  const [modifyingStructure, setModifyingStructure] = useState(false);
  const [newTableName, setNewTableName] = useState(tableName);
  const [structureColumns, setStructureColumns] = useState([]);
  const [supportsNonPkAutoincrement, setSupportsNonPkAutoincrement] =
    useState(true); // Default true
  const [checkConstraints, setCheckConstraints] = useState({});
  const [showCheckEditors, setShowCheckEditors] = useState({});

  // Triggers state
  const [triggers, setTriggers] = useState([]);
  const [supportsTriggers, setSupportsTriggers] = useState(false);
  const [showEditTriggerModal, setShowEditTriggerModal] = useState(false);
  const [editingTrigger, setEditingTrigger] = useState(null);
  const [triggerForm, setTriggerForm] = useState({
    trigger_name: "",
    trigger_timing: "BEFORE",
    trigger_event: "INSERT",
    trigger_body: "",
  });

  // Procedures state
  const [procedures, setProcedures] = useState([]);
  const [supportsProcedures, setSupportsProcedures] = useState(false);
  const [procedureCode, setProcedureCode] = useState("");
  const [showEditProcedureModal, setShowEditProcedureModal] = useState(false);
  const [editingProcedure, setEditingProcedure] = useState(null);

  // PL/SQL state
  const [plsqlCode, setPlsqlCode] = useState("");
  const [supportsPlsql, setSupportsPlsql] = useState(false);

  // Charts state
  const [chartData, setChartData] = useState(null);
  const [chartKeys, setChartKeys] = useState([]);
  const [chartType, setChartType] = useState("bar");
  const [labelField, setLabelField] = useState("");
  const [dataFields, setDataFields] = useState([]);
  const [chartInstance, setChartInstance] = useState(null);
  const chartRef = useRef(null);

  // DB info
  const [dbType, setDbType] = useState("sql");
  const [handlerName, setHandlerName] = useState("");
  const [primaryKeyColumn, setPrimaryKeyColumn] = useState(null);

  // Fetch table data
  useEffect(() => {
    fetchTableData();
    fetchCapabilities();
  }, [dbName, tableName, page, sortColumn, sortOrder]);

  // Fetch additional data based on tab
  useEffect(() => {
    if (tab === "triggers") {
      fetchTriggers();
    } else if (tab === "procedures") {
      fetchProcedures();
    } else if (tab === "structure") {
      fetchStructure();
    } else if (tab === "charts") {
      fetchChartData();
    }
  }, [tab]);

  useEffect(() => {
    if (searchTerm) {
      performSearch(searchTerm, selectedFields);
    }
  }, [page]);

  const fetchTableData = async () => {
    try {
      setLoading(true);
      setError("");
      const response = await axios.get(`/api/table/${dbName}/${tableName}`, {
        params: {
          page,
          per_page: perPage,
          sort_column: sortColumn,
          sort_order: sortOrder,
        },
      });

      if (response.data.success) {
        setColumns(response.data.columns);
        setRows(response.data.rows);
        setAllRows(response.data.rows);
        setRecordCount(response.data.record_count);
        setTotalPages(response.data.total_pages);
        setDbType(response.data.db_type);
        setHandlerName(response.data.handler);

        const pkCol = response.data.columns.find((col) => col.pk);
        setPrimaryKeyColumn(pkCol ? pkCol.name : null);

        const initialData = {};
        response.data.columns.forEach((col) => {
          initialData[col.name] = "";
        });
        setFormData(initialData);

        // ✅ Check feature support from handler
        checkFeatureSupport();
      } else {
        setError(response.data.error || "Failed to fetch table data");
      }
    } catch (err) {
      console.error("Failed to fetch table data:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchCapabilities = async () => {
    try {
      const response = await axios.get(`/api/db/${dbName}/capabilities`);
      if (response.data.success) {
        setSupportsNonPkAutoincrement(
          response.data.capabilities.supports_non_pk_autoincrement
        );
      }
    } catch (err) {
      console.error("Failed to fetch capabilities:", err);
      // Default to true (allow autoincrement on non-PK)
      setSupportsNonPkAutoincrement(true);
    }
  };

  const checkFeatureSupport = async () => {
    try {
      // Check triggers support
      const triggersResponse = await axios.get(
        `/api/table/${dbName}/${tableName}/triggers`
      );
      if (triggersResponse.data.success) {
        setSupportsTriggers(triggersResponse.data.supports_triggers);
      }
    } catch (err) {
      console.error("Failed to check triggers support:", err);
      setSupportsTriggers(false);
    }

    try {
      // Check procedures support
      const proceduresResponse = await axios.get(
        `/api/table/${dbName}/${tableName}/procedures`
      );
      if (proceduresResponse.data.success) {
        setSupportsProcedures(proceduresResponse.data.supports_procedures);
      }
    } catch (err) {
      console.error("Failed to check procedures support:", err);
      setSupportsProcedures(false);
    }

    try {
      // ✅ Check PL/SQL support via API
      const plsqlResponse = await axios.get(
        `/api/table/${dbName}/${tableName}/plsql/support`
      );
      if (plsqlResponse.data.success) {
        setSupportsPlsql(plsqlResponse.data.supports_plsql);
      }
    } catch (err) {
      console.error("Failed to check PL/SQL support:", err);
      setSupportsPlsql(false);
    }
  };

  const canSupportAutoincrement = (type, handlerName) => {
    if (handlerName === "PostgreSQL") {
      // PostgreSQL uses SERIAL types for autoincrement
      const autoincrementTypes = [
        "SERIAL",
        "BIGSERIAL",
        "SMALLSERIAL",
        "INTEGER",
        "BIGINT",
        "SMALLINT",
      ];
      return autoincrementTypes.includes(type?.toUpperCase());
    } else if (handlerName === "MySQL") {
      const autoincrementTypes = [
        "INT",
        "INTEGER",
        "BIGINT",
        "SMALLINT",
        "TINYINT",
        "MEDIUMINT",
      ];
      return autoincrementTypes.includes(type?.toUpperCase());
    } else {
      // SQLite and others
      const autoincrementTypes = [
        "INTEGER",
        "INT",
        "BIGINT",
        "SMALLINT",
        "TINYINT",
      ];
      return autoincrementTypes.includes(type?.toUpperCase());
    }
  };

  const fetchStructure = async () => {
    try {
      const response = await axios.get(
        `/api/table/${dbName}/${tableName}/structure`
      );
      if (response.data.success) {
        setTypes(response.data.types);

        // ✅ Extract check constraints from columns
        const checks = {};
        response.data.columns.forEach((col) => {
          if (col.check_constraint) {
            checks[col.name] = col.check_constraint;
          }
        });
        setCheckConstraints(checks);

        setStructureColumns(
          response.data.columns.map((col, idx) => ({
            ...col,
            index: idx + 1,
            autoincrement: Boolean(col.autoincrement),
            unique: Boolean(col.unique),
            has_check: Boolean(col.check_constraint),
          }))
        );
        setNewTableName(response.data.table_name);
      }
    } catch (err) {
      console.error("Failed to fetch structure:", err);
      setError("Failed to load structure");
    }
  };

  const fetchTriggers = async () => {
    try {
      const response = await axios.get(
        `/api/table/${dbName}/${tableName}/triggers`
      );
      if (response.data.success) {
        setTriggers(response.data.triggers);
        setSupportsTriggers(response.data.supports_triggers);
      }
    } catch (err) {
      console.error("Failed to fetch triggers:", err);
    }
  };

  const fetchProcedures = async () => {
    try {
      const response = await axios.get(
        `/api/table/${dbName}/${tableName}/procedures`
      );
      if (response.data.success) {
        setProcedures(response.data.procedures);
        setSupportsProcedures(response.data.supports_procedures);
      }
    } catch (err) {
      console.error("Failed to fetch procedures:", err);
    }
  };

  const handleExecuteSpecificProcedure = async (procedureName) => {
    setError("");
    setMessage("");
    setQueryResult(null);

    try {
      const response = await axios.post(
        `/api/db/${dbName}/procedure/${procedureName}/execute`
      );

      if (response.data.success) {
        const result = response.data.result;
        const resultType = response.data.result_type;

        setMessage(response.data.message);

        if (
          resultType === "table" &&
          Array.isArray(result) &&
          result.length > 0
        ) {
          setQueryResult(result);
        } else if (resultType === "status") {
          if (result && typeof result === "object") {
            const statusMsg =
              result.status || result.message || JSON.stringify(result);
            setMessage(statusMsg);
          }
          setQueryResult(null);
        } else {
          setQueryResult(null);
        }
      } else {
        setError(response.data.error || "Failed to execute procedure");
      }
    } catch (err) {
      setError(
        "Failed to execute procedure: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  const handleOpenEditProcedure = (proc) => {
    setEditingProcedure(proc);
    setShowEditProcedureModal(true);
  };

  const fetchChartData = async () => {
    try {
      const response = await axios.get(
        `/api/table/${dbName}/${tableName}/chart_data`
      );
      if (response.data.success) {
        setChartData(response.data.data);
        setChartKeys(response.data.keys);
        if (response.data.keys.length > 0) {
          setLabelField(response.data.keys[0]);
        }
      }
    } catch (err) {
      console.error("Failed to fetch chart data:", err);
      setError("Failed to load chart data");
    }
  };

  const performSearch = async (term, fields) => {
    setSearching(true);
    try {
      const fieldsParam = fields.size > 0 ? Array.from(fields).join(",") : "";
      const response = await axios.get(
        `/api/table/${dbName}/${tableName}/search`,
        {
          params: {
            q: term,
            fields: fieldsParam,
            page,
            per_page: perPage,
          },
        }
      );

      if (response.data.success) {
        setRows(response.data.rows);
        setRecordCount(response.data.total);
        setTotalPages(response.data.total_pages);
      }
    } catch (err) {
      console.error("Search error:", err);
    } finally {
      setSearching(false);
    }
  };

  const handleQueryKeyDown = (e) => {
    // First, try autocomplete
    const handled = handleAutocompleteKeyDown(e, queryText, (selected) => {
      setQueryText(selected);
      resetNavigation();
    });

    if (handled) return;

    // Then handle history navigation
    if (e.key === "ArrowUp" && sessionQueries.length > 0) {
      e.preventDefault();
      const previousQuery = navigateHistory("up", queryText);
      if (previousQuery !== null) {
        setQueryText(previousQuery);
      }
    } else if (e.key === "ArrowDown" && sessionQueries.length > 0) {
      e.preventDefault();
      const nextQuery = navigateHistory("down", queryText);
      if (nextQuery !== null) {
        setQueryText(nextQuery);
      }
    }
  };

  const handleSearchChange = (value) => {
    setSearchTerm(value);

    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }

    const timeout = setTimeout(() => {
      performSearch(value, selectedFields);
    }, 300);

    setSearchTimeout(timeout);
  };

  const handleFieldToggle = (fieldName, checked) => {
    const newSelected = new Set(selectedFields);
    if (checked) {
      newSelected.add(fieldName);
    } else {
      newSelected.delete(fieldName);
    }
    setSelectedFields(newSelected);

    // Re-search with new fields
    if (searchTerm) {
      performSearch(searchTerm, newSelected);
    }
  };

  const handleSort = (column) => {
    if (sortColumn === column) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortColumn(column);
      setSortOrder("asc");
    }
    setPage(1);
  };

  const handleTabChange = (newTab) => {
    setTab(newTab);
    setSearchParams({ tab: newTab });
    setError("");
    setMessage("");
    setQueryResult(null);
  };

  const handleInputChange = (columnName, value) => {
    setFormData({
      ...formData,
      [columnName]: value,
    });
  };

  const handleInsert = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    // ✅ CRITICAL: Validate ALL required fields
    for (const col of columns) {
      const value = formData[col.name];
      const isEmpty = !value || value === "";

      // ✅ PRIMARY KEY without autoincrement MUST have a value
      if (col.pk && !col.autoincrement && isEmpty) {
        setError(
          `${col.name} is a primary key without autoincrement - you must provide a value`
        );
        return;
      }

      // ✅ NOT NULL fields (except autoincrement) MUST have values
      if (col.notnull && !col.autoincrement && isEmpty) {
        setError(`${col.name} cannot be empty (NOT NULL constraint)`);
        return;
      }
    }

    // ✅ Build data object - exclude empty autoincrement fields, include everything else
    const cleanData = {};
    Object.keys(formData).forEach((key) => {
      const col = columns.find((c) => c.name === key);
      const value = formData[key];

      if (col) {
        // Include if: has a value OR is required (PK/NOT NULL without autoincrement)
        if (value !== "") {
          cleanData[key] = value;
        } else if (col.pk && !col.autoincrement) {
          // Empty PK without autoincrement should have been caught by validation
          // but include it to trigger server-side error
          cleanData[key] = value;
        }
      }
    });

    try {
      const response = await axios.post(
        `/api/table/${dbName}/${tableName}/data`,
        {
          action: "insert",
          data: cleanData,
        }
      );

      if (response.data.success) {
        setMessage("Row inserted successfully");
        const clearedData = {};
        columns.forEach((col) => {
          clearedData[col.name] = "";
        });
        setFormData(clearedData);
        setShowInsertModal(false);
        fetchTableData();
      } else {
        setError(response.data.error || "Failed to insert row");
      }
    } catch (err) {
      setError(
        "Failed to insert row: " + (err.response?.data?.error || err.message)
      );
    }
  };

  const handleUpdateInputChange = (columnName, value) => {
    setUpdateFormData({
      ...updateFormData,
      [columnName]: value,
    });
  };

  const handleUpdate = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    if (!updateCondition.trim()) {
      setError("Update condition (WHERE clause) is required");
      return;
    }

    // Filter out empty values
    const data = {};
    Object.keys(updateFormData).forEach((key) => {
      if (updateFormData[key]) {
        data[key] = updateFormData[key];
      }
    });

    if (Object.keys(data).length === 0) {
      setError("At least one column value must be provided for update");
      return;
    }

    try {
      const response = await axios.post(
        `/api/table/${dbName}/${tableName}/data`,
        {
          action: "update",
          data: data,
          condition: updateCondition,
        }
      );
      if (response.data.success) {
        setMessage("Rows updated successfully");
        setUpdateFormData({});
        setUpdateCondition("");
        setShowUpdateModal(false);
        fetchTableData();
      } else {
        setError(response.data.error || "Failed to update rows");
      }
    } catch (err) {
      setError(
        "Failed to update rows: " + (err.response?.data?.error || err.message)
      );
    }
  };
  const handleDeleteBulk = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");
    if (!deleteCondition.trim()) {
      setError("Delete condition (WHERE clause) is required");
      return;
    }
    if (
      !window.confirm(
        `Are you sure you want to delete rows WHERE ${deleteCondition}?`
      )
    ) {
      return;
    }
    try {
      const response = await axios.post(
        `/api/table/${dbName}/${tableName}/data`,
        {
          action: "delete",
          condition: deleteCondition,
        }
      );
      if (response.data.success) {
        setMessage("Rows deleted successfully");
        setDeleteCondition("");
        setShowDeleteModal(false);
        fetchTableData();
      } else {
        setError(response.data.error || "Failed to delete rows");
      }
    } catch (err) {
      setError(
        "Failed to delete rows: " + (err.response?.data?.error || err.message)
      );
    }
  };

  const handleModify = (row) => {
    // ✅ Use entire row as identifier if no primary key
    if (primaryKeyColumn) {
      setEditingRowId(row[primaryKeyColumn]);
    } else {
      // Store entire row as JSON string to use as identifier
      setEditingRowId(JSON.stringify(row));
    }
    setFormData(row);
  };

  const handleSave = async () => {
    setError("");
    setMessage("");

    if (!editingRowId) {
      setError("Cannot save: no row identifier");
      return;
    }

    // ✅ Build condition based on primary key OR all columns
    let condition = "";
    let originalRowData = {};

    if (primaryKeyColumn) {
      // Has primary key - use it
      condition = `${primaryKeyColumn} = '${editingRowId}'`;
    } else {
      // No primary key - parse original row data from editingRowId
      try {
        originalRowData = JSON.parse(editingRowId);
      } catch (e) {
        setError("Cannot save: invalid row identifier");
        return;
      }
    }

    try {
      const response = await axios.post(
        `/api/table/${dbName}/${tableName}/data`,
        {
          action: "update",
          data: formData,
          condition: condition || undefined,
          // ✅ CRITICAL: Always send original_data when no primary key
          original_data: !primaryKeyColumn ? originalRowData : undefined,
        }
      );

      if (response.data.success) {
        setMessage("Row updated successfully");
        setEditingRowId(null);
        fetchTableData();
      } else {
        setError(response.data.error || "Failed to update row");
      }
    } catch (err) {
      setError(
        "Failed to update row: " + (err.response?.data?.error || err.message)
      );
    }
  };

  const handleCancelEdit = () => {
    setEditingRowId(null);
    const clearedData = {};
    columns.forEach((col) => {
      clearedData[col.name] = "";
    });
    setFormData(clearedData);
  };

  const handleDelete = async (row) => {
    if (!window.confirm("Are you sure you want to delete this row?")) {
      return;
    }

    // ✅ Build condition based on primary key OR all columns
    let condition = "";

    if (primaryKeyColumn) {
      // Has primary key - use it
      condition = `${primaryKeyColumn} = '${row[primaryKeyColumn]}'`;
    }
    // ✅ If no primary key, backend will build condition from row data

    try {
      const response = await axios.post(
        `/api/table/${dbName}/${tableName}/data`,
        {
          action: "delete",
          condition: condition || undefined,
          // ✅ Send entire row data if no primary key
          ...(!primaryKeyColumn && { data: row }),
        }
      );

      if (response.data.success) {
        setMessage("Row deleted successfully");
        fetchTableData();
      } else {
        setError(response.data.error || "Failed to delete row");
      }
    } catch (err) {
      setError(
        "Failed to delete row: " + (err.response?.data?.error || err.message)
      );
    }
  };

  // ✅ FIXED: handleStructureColumnChange - proper state management
  const handleStructureColumnChange = (index, field, value) => {
    setStructureColumns((prev) => {
      const updated = [...prev];

      // ✅ Handle autoincrement ENABLE
      if (field === "autoincrement" && value === true) {
        return updated.map((col, i) => {
          if (i === index) {
            // This column is being SET as autoincrement
            return {
              ...col,
              autoincrement: true,
              unique: true, // Autoincrement requires unique
              notnull: true, // Autoincrement implies NOT NULL
            };
          } else {
            // ✅ FIX: Remove autoincrement from OTHER columns
            // AND reset their unique/notnull if they're NOT primary keys
            if (col.autoincrement) {
              return {
                ...col,
                autoincrement: false,
                unique: col.pk ? true : false, // Keep only if PK
                notnull: col.pk ? true : false, // Keep only if PK
              };
            }
            return col;
          }
        });
      }

      // ✅ Handle autoincrement DISABLE
      if (field === "autoincrement" && value === false) {
        return updated.map((col, i) => {
          if (i === index) {
            return {
              ...col,
              autoincrement: false,
              // ✅ CRITICAL FIX: When disabling autoincrement, reset unique and notnull
              // UNLESS the column is a primary key (PK always needs unique/notnull)
              unique: col.pk ? true : false, // Keep unique only if PK
              notnull: col.pk ? true : false, // Keep notnull only if PK
            };
          }
          return col;
        });
      }

      // ✅ Prevent unchecking unique when autoincrement is active
      if (
        field === "unique" &&
        value === false &&
        updated[index].autoincrement
      ) {
        // Can't uncheck unique when autoincrement is enabled
        return updated;
      }

      // ✅ Prevent unchecking notnull when autoincrement is active
      if (
        field === "notnull" &&
        value === false &&
        updated[index].autoincrement
      ) {
        // Can't uncheck NOT NULL when autoincrement is enabled
        return updated;
      }

      // Default behavior for other fields
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const handlePKChange = (index, checked) => {
    setStructureColumns((prev) => {
      return prev.map((col, i) => {
        if (i === index) {
          // THIS column is being checked/unchecked as PK
          return {
            ...col,
            pk: checked,
            notnull: checked,
            unique: checked, // PK is always unique
          };
        } else if (col.pk && checked) {
          // ✅ ONLY if checking NEW PK: remove PK from OLD PK column
          return {
            ...col,
            pk: false,
            notnull: false, // ✅ Remove not null from old PK
            unique: false, // ✅ Remove unique from old PK
          };
        } else {
          // ✅ Leave other columns unchanged
          return col;
        }
      });
    });
  };

  const handleAddStructureColumn = () => {
    setStructureColumns([
      ...structureColumns,
      {
        index: structureColumns.length + 1,
        name: "",
        type: types[0] || "TEXT",
        pk: false,
        notnull: false,
        autoincrement: false,
      },
    ]);
  };

  const handleDeleteStructureColumn = (index) => {
    if (structureColumns.length === 1) {
      setError(
        "Cannot delete the last column. At least one column is required."
      );
      return;
    }

    if (!window.confirm("Are you sure you want to delete this column?")) {
      return;
    }

    const updated = structureColumns.filter((_, idx) => idx !== index);
    setStructureColumns(updated);
  };

  // ✅ FIXED: handleStructureSubmit - proper column data construction
  const handleStructureSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    // Validate table name
    if (!newTableName.match(/^[a-zA-Z][a-zA-Z0-9_]*$/)) {
      setError(
        "Table name must start with a letter and contain only letters, numbers, underscores."
      );
      return;
    }

    // Validate columns
    const columnNames = new Set();
    let hasPK = false;

    for (const col of structureColumns) {
      if (!col.name || !col.type) {
        setError("All columns must have a name and type.");
        return;
      }

      if (columnNames.has(col.name)) {
        setError(`Duplicate column name: ${col.name}`);
        return;
      }
      columnNames.add(col.name);

      if (col.pk) {
        if (hasPK) {
          setError("Only one primary key is allowed.");
          return;
        }
        hasPK = true;
      }
    }

    // ✅ FIXED: Prepare columns data with CHECK constraints
    const columnsData = structureColumns.map((col) => {
      const isActuallyUnique = col.autoincrement || col.pk || col.unique;
      const isActuallyNotNull = col.autoincrement || col.pk || col.notnull;

      const colData = {
        name: col.name,
        type: col.type,
        is_pk: col.pk || false,
        is_not_null: isActuallyNotNull,
        is_autoincrement: Boolean(col.autoincrement),
        is_unique: isActuallyUnique,
      };

      // ✅ CRITICAL: Add CHECK constraint if present
      const checkExpr = checkConstraints[col.name];
      if (checkExpr && checkExpr.trim()) {
        colData.check_constraint = checkExpr.trim();
      }

      return colData;
    });

    try {
      const response = await axios.post(
        `/api/table/${dbName}/${tableName}/structure`,
        {
          new_table_name: newTableName,
          columns: columnsData,
        }
      );

      if (response.data.success) {
        setMessage(
          response.data.message || "Table structure updated successfully"
        );
        setModifyingStructure(false);

        // If table name changed, navigate to new table
        if (
          response.data.new_table_name &&
          response.data.new_table_name !== tableName
        ) {
          setTimeout(() => {
            navigate(
              `/db/${dbName}/table/${response.data.new_table_name}?tab=structure`
            );
            window.location.reload();
          }, 1000);
        } else {
          // Refresh structure
          fetchStructure();
          fetchTableData();
        }
      } else {
        setError(response.data.error || "Failed to update structure");
      }
    } catch (err) {
      setError(
        "Failed to update structure: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  const handleQuerySubmit = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");
    setQueryResult(null);

    if (!queryText.trim()) {
      setError("Query cannot be empty");
      return;
    }

    try {
      const response = await axios.post(
        `/api/table/${dbName}/${tableName}/query`,
        {
          query: queryText,
        }
      );

      if (response.data.success) {
        const result = response.data.result;
        const resultType = response.data.result_type;

        await addQuery(queryText);

        console.log("Query result:", result);
        console.log("Result type:", resultType);

        // Handle different result types
        if (
          resultType === "table" &&
          Array.isArray(result) &&
          result.length > 0
        ) {
          setQueryResult(result);
          setMessage("Query executed successfully");
        } else if (resultType === "status") {
          if (result && typeof result === "object") {
            if (result.rows_affected !== undefined) {
              setMessage(
                `Query executed successfully. ${result.rows_affected} rows affected.`
              );
            } else {
              const statusMsg =
                result.status || result.message || JSON.stringify(result);
              setMessage(statusMsg);
            }
          }
          setQueryResult(null);
        } else if (resultType === "empty") {
          setMessage("Query executed successfully. No results returned.");
          setQueryResult(null);
        } else {
          // Fallback for backwards compatibility
          setQueryResult(result);
          setMessage("Query executed successfully");
        }
      } else {
        setError(response.data.error || "Query execution failed");
      }
    } catch (err) {
      setError(
        "Failed to execute query: " + (err.response?.data?.error || err.message)
      );
    }
  };

  const handleCreateTrigger = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    try {
      const response = await axios.post(
        `/api/table/${dbName}/${tableName}/triggers`,
        triggerForm
      );

      if (response.data.success) {
        setMessage("Trigger created successfully");
        setTriggerForm({
          trigger_name: "",
          trigger_timing: "BEFORE",
          trigger_event: "INSERT",
          trigger_body: "",
        });
        fetchTriggers();
      } else {
        setError(response.data.error || "Failed to create trigger");
      }
    } catch (err) {
      setError(
        "Failed to create trigger: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  const handleEditTrigger = (trigger) => {
    setEditingTrigger(trigger);
    setShowEditTriggerModal(true);
  };

  const handleDeleteTrigger = async (triggerName) => {
    if (!window.confirm(`Delete trigger ${triggerName}?`)) return;

    try {
      const response = await axios.delete(
        `/api/table/${dbName}/${tableName}/triggers`,
        {
          data: { trigger_name: triggerName },
        }
      );

      if (response.data.success) {
        setMessage("Trigger deleted successfully");
        fetchTriggers();
      } else {
        setError(response.data.error || "Failed to delete trigger");
      }
    } catch (err) {
      setError(
        "Failed to delete trigger: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  const handleExecuteProcedure = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    try {
      const response = await axios.post(
        `/api/table/${dbName}/${tableName}/procedures`,
        {
          procedure_code: procedureCode,
        }
      );

      if (response.data.success) {
        setMessage(response.data.message || "Procedure executed successfully");

        // ✅ FIX: Handle different result types
        const result = response.data.result;
        const resultType = response.data.result_type;

        if (
          resultType === "table" &&
          Array.isArray(result) &&
          result.length > 0
        ) {
          // Table data - display in queryResult
          setQueryResult(result);
        } else if (resultType === "status") {
          // Status message - show in message area
          if (result && typeof result === "object") {
            const statusMsg =
              result.status || result.message || JSON.stringify(result);
            setMessage(statusMsg);
          }
          setQueryResult(null);
        } else {
          setQueryResult(null);
        }

        setProcedureCode("");
        fetchProcedures();
      } else {
        setError(response.data.error || "Failed to execute procedure");
      }
    } catch (err) {
      setError(
        "Failed to execute procedure: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  const handleExecutePlsql = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    try {
      const response = await axios.post(
        `/api/table/${dbName}/${tableName}/plsql`,
        {
          plsql_code: plsqlCode,
        }
      );

      if (response.data.success) {
        if (response.data.refresh) {
          setMessage(response.data.status);
          fetchTableData();
        } else {
          setMessage(response.data.message || "PL/SQL executed successfully");
          setQueryResult(response.data.result);
        }
        setPlsqlCode("");
      } else {
        setError(response.data.error || "Failed to execute PL/SQL");
      }
    } catch (err) {
      setError(
        "Failed to execute PL/SQL: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  const toggleFilterMenu = () => {
    setShowFilterMenu(!showFilterMenu);
  };

  const toggleField = handleFieldToggle;

  const {
    suggestions: autocompleteSuggestions,
    showSuggestions: showAutocompleteSuggestions,
    selectedIndex: autocompleteSelectedIndex,
    handleQueryChange: handleAutocompleteChange,
    handleKeyDown: handleAutocompleteKeyDown,
    selectSuggestion: selectAutocompleteSuggestion,
    hideSuggestions: hideAutocompleteSuggestions,
  } = useAutocomplete();

  if (loading) {
    return (
      <>
        <Sidebar dbType={dbType} handlerName={handlerName} />
        <div className="center">
          <div className="loading">Loading table data...</div>
        </div>
      </>
    );
  }

  return (
    <>
      <Sidebar dbType={dbType} handlerName={handlerName} />
      <div className="center">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "10px",
          }}
        >
          <h2 style={{ margin: 0, color: "#f0f0f0" }}>
            Table: {tableName} in {dbName} ({dbType.toUpperCase()})
          </h2>
          <span
            style={{ color: "#ccc", fontStyle: "italic", fontSize: "0.9em" }}
          >
            {recordCount} record{recordCount !== 1 ? "s" : ""}
          </span>
        </div>

        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate(`/db/${dbName}`);
          }}
          style={{ color: "#bb86fc" }}
        >
          ← Back to Tables
        </a>
        <br />
        <br />

        {error && <div className="error">{error}</div>}
        {message && <div className="success">{message}</div>}

        <div className="tabs">
          <button
            className="tab-button"
            onClick={() => handleTabChange("data")}
            style={{ background: tab === "data" ? "#4b0082" : "#9370db" }}
          >
            Data
          </button>
          <button
            className="tab-button"
            onClick={() => handleTabChange("structure")}
            style={{ background: tab === "structure" ? "#4b0082" : "#9370db" }}
          >
            Structure
          </button>
          <button
            className="tab-button"
            onClick={() => handleTabChange("query")}
            style={{ background: tab === "query" ? "#4b0082" : "#9370db" }}
          >
            Query
          </button>
          <button
            className="tab-button"
            onClick={() => handleTabChange("importexport")}
            style={{
              background: tab === "importexport" ? "#4b0082" : "#9370db",
            }}
          >
            Import/Export
          </button>
          {supportsProcedures && (
            <button
              className="tab-button"
              onClick={() => handleTabChange("procedures")}
              style={{
                background: tab === "procedures" ? "#4b0082" : "#9370db",
              }}
            >
              Procedures
            </button>
          )}
          {supportsTriggers && (
            <button
              className="tab-button"
              onClick={() => handleTabChange("triggers")}
              style={{ background: tab === "triggers" ? "#4b0082" : "#9370db" }}
            >
              Triggers
            </button>
          )}
          {supportsPlsql && (
            <button
              className="tab-button"
              onClick={() => handleTabChange("plsql")}
              style={{ background: tab === "plsql" ? "#4b0082" : "#9370db" }}
            >
              PL/SQL
            </button>
          )}
          <button
            className="tab-button"
            onClick={() => handleTabChange("charts")}
            style={{ background: tab === "charts" ? "#4b0082" : "#9370db" }}
          >
            Charts
          </button>
        </div>

        {/* DATA TAB */}
        {tab === "data" && (
          <div>
            <div style={{ margin: "20px 0", textAlign: "left" }}>
              <input
                type="text"
                placeholder="Search in selected fields..."
                value={searchTerm}
                onChange={(e) => handleSearchChange(e.target.value)}
                style={{
                  padding: "8px 20px",
                  width: "550px",
                  maxWidth: "90%",
                  border: "1.5px solid #9370db",
                  borderRadius: "10px",
                  fontSize: "16px",
                  background: "rgba(147, 112, 219, 0.1)",
                  color: "#f0f0f0",
                }}
              />
              <button
                onClick={toggleFilterMenu}
                style={{
                  marginLeft: "10px",
                  padding: "14px 22px",
                  background: "linear-gradient(135deg, #6a5acd, #483d8b)",
                  color: "white",
                  border: "none",
                  borderRadius: "10px",
                  cursor: "pointer",
                  fontWeight: "bold",
                }}
              >
                Filter Fields
              </button>
              <button
                onClick={() => {
                  setSearchTerm("");
                  setSelectedFields(new Set());
                  setRows(allRows);
                }}
                style={{
                  marginLeft: "10px",
                  padding: "14px 22px",
                  background: "#6c757d",
                  color: "white",
                  border: "none",
                  borderRadius: "10px",
                  cursor: "pointer",
                }}
              >
                Clear
              </button>

              {showFilterMenu && (
                <div
                  style={{
                    marginTop: "15px",
                    padding: "20px",
                    background: "#fff",
                    color: "#333",
                    borderRadius: "15px",
                    boxShadow: "0 10px 30px rgba(0,0,0,0.2)",
                    maxWidth: "600px",
                    maxHeight: "320px",
                    overflowY: "auto",
                  }}
                >
                  <strong style={{ color: "#4b0082" }}>
                    Choose fields to search in:
                  </strong>
                  <br />
                  <br />
                  {columns.map((col) => (
                    <div key={col.name} style={{ margin: "8px 0" }}>
                      <label
                        style={{
                          cursor: "pointer",
                          display: "block",
                          padding: "4px 0",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={selectedFields.has(col.name)}
                          onChange={(e) =>
                            toggleField(col.name, e.target.checked)
                          }
                          style={{ marginRight: "10px" }}
                        />
                        <span>{col.name}</span>
                      </label>
                    </div>
                  ))}
                </div>
              )}

              {selectedFields.size > 0 && (
                <div
                  style={{
                    marginTop: "10px",
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "10px",
                  }}
                >
                  {Array.from(selectedFields).map((field) => (
                    <span
                      key={field}
                      style={{
                        background: "linear-gradient(135deg,#e91e63,#ad1457)",
                        color: "white",
                        padding: "2px 20px",
                        borderRadius: "30px",
                        fontWeight: "600",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "10px",
                      }}
                    >
                      {field}
                      <span
                        onClick={() => toggleField(field, false)}
                        style={{
                          cursor: "pointer",
                          fontWeight: "600",
                          fontSize: "1.2em",
                        }}
                      >
                        ×
                      </span>
                    </span>
                  ))}
                </div>
              )}

              {searchTerm && (
                <div
                  style={{ marginTop: "8px", fontSize: "14px", color: "#ccc" }}
                >
                  {searching ? (
                    <span style={{ color: "#6a5acd" }}>🔍 Searching...</span>
                  ) : rows.length === 0 ? (
                    <span style={{ color: "#dc3545" }}>
                      ⚠️ No results found.
                    </span>
                  ) : (
                    <span style={{ color: "#28a745" }}>
                      ✓ {recordCount} record{recordCount !== 1 ? "s" : ""} match
                    </span>
                  )}
                </div>
              )}
            </div>

            <div style={{ display: "flex", gap: "15px", marginBottom: "20px" }}>
              <button
                onClick={() => {
                  // Reset formData to clean state when opening insert modal
                  const cleanData = {};
                  columns.forEach((col) => {
                    cleanData[col.name] = "";
                  });
                  setFormData(cleanData);
                  setShowInsertModal(true);
                }}
                style={{
                  padding: "14px 28px",
                  background: "linear-gradient(135deg, #6a5acd, #483d8b)",
                  color: "white",
                  border: "none",
                  borderRadius: "8px",
                  cursor: "pointer",
                  fontWeight: "bold",
                  boxShadow: "0 4px 20px rgba(106, 90, 205, 0.5)",
                }}
              >
                📄 Insert Row
              </button>
              <button
                onClick={() => setShowUpdateModal(true)}
                style={{
                  padding: "14px 28px",
                  background: "linear-gradient(135deg, #1e9530, #145a21)",
                  color: "white",
                  border: "none",
                  borderRadius: "8px",
                  cursor: "pointer",
                  fontWeight: "bold",
                  boxShadow: "0 4px 20px rgba(30, 149, 48, 0.5)",
                }}
              >
                ✏️ Update Rows
              </button>
              <button
                onClick={() => setShowDeleteModal(true)}
                style={{
                  padding: "14px 28px",
                  background: "linear-gradient(135deg, #dc3545, #a71d2a)",
                  color: "white",
                  border: "none",
                  borderRadius: "8px",
                  cursor: "pointer",
                  fontWeight: "bold",
                  boxShadow: "0 4px 20px rgba(220, 53, 69, 0.5)",
                }}
              >
                🗑️ Delete Rows
              </button>
            </div>

            {/* Pagination - Top */}
            {totalPages > 1 && (
              <div className="pagination" style={{ marginBottom: "20px" }}>
                {page > 1 ? (
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      setPage(page - 1);
                    }}
                  >
                    ← Previous
                  </a>
                ) : (
                  <span className="disabled">← Previous</span>
                )}
                <span className="current">
                  Page {page} of {totalPages} ({recordCount} total)
                </span>
                {page < totalPages ? (
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      setPage(page + 1);
                    }}
                  >
                    Next →
                  </a>
                ) : (
                  <span className="disabled">Next →</span>
                )}
              </div>
            )}

            {totalPages > 1 && (
              <div className="pagination">
                {page > 1 ? (
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      setPage(page - 1);
                    }}
                  >
                    ← Previous
                  </a>
                ) : (
                  <span className="disabled">← Previous</span>
                )}
                <span className="current">
                  Page {page} of {totalPages} ({recordCount} total)
                </span>
                {page < totalPages ? (
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      setPage(page + 1);
                    }}
                  >
                    Next →
                  </a>
                ) : (
                  <span className="disabled">Next →</span>
                )}
              </div>
            )}

            <div style={{ overflowX: "auto" }}>
              <table className="result-table">
                <thead>
                  <tr>
                    {columns.map((col) => (
                      <th
                        key={col.name}
                        onClick={() => handleSort(col.name)}
                        style={{ cursor: "pointer" }}
                      >
                        {col.name}
                        {sortColumn === col.name && (
                          <span style={{ marginLeft: "4px" }}>
                            {sortOrder === "asc" ? "▲" : "▼"}
                          </span>
                        )}
                      </th>
                    ))}
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length > 0 ? (
                    rows.map((row, idx) => (
                      <tr key={idx}>
                        {(
                          primaryKeyColumn
                            ? editingRowId === row[primaryKeyColumn]
                            : editingRowId === JSON.stringify(row)
                        ) ? (
                          <>
                            {columns.map((col) => (
                              <td key={col.name}>
                                <input
                                  type={
                                    col.type === "INTEGER" ||
                                    col.type === "REAL"
                                      ? "number"
                                      : "text"
                                  }
                                  value={formData[col.name] ?? ""}
                                  onChange={(e) =>
                                    handleInputChange(col.name, e.target.value)
                                  }
                                  required={col.notnull}
                                  style={{ width: "100px", padding: "4px" }}
                                />
                              </td>
                            ))}
                            <td>
                              <button
                                onClick={handleSave}
                                style={{
                                  background: "#008000",
                                  marginRight: "5px",
                                }}
                              >
                                Save
                              </button>
                              <button
                                onClick={handleCancelEdit}
                                style={{ background: "#ff0000" }}
                              >
                                Cancel
                              </button>
                            </td>
                          </>
                        ) : (
                          <>
                            {columns.map((col) => (
                              <td key={col.name}>{row[col.name] ?? ""}</td>
                            ))}
                            <td>
                              <button
                                onClick={() => handleModify(row)}
                                style={{
                                  background: "#008000",
                                  marginRight: "5px",
                                }}
                              >
                                Modify
                              </button>
                              <button
                                onClick={() => handleDelete(row)}
                                style={{ background: "#ff0000" }}
                              >
                                Delete
                              </button>
                            </td>
                          </>
                        )}
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td
                        colSpan={columns.length + 1}
                        style={{ textAlign: "center", color: "#666" }}
                      >
                        No records available
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="pagination">
                {page > 1 ? (
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      setPage(page - 1);
                    }}
                  >
                    ← Previous
                  </a>
                ) : (
                  <span className="disabled">← Previous</span>
                )}
                <span className="current">
                  Page {page} of {totalPages} ({recordCount} total)
                </span>
                {page < totalPages ? (
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      setPage(page + 1);
                    }}
                  >
                    Next →
                  </a>
                ) : (
                  <span className="disabled">Next →</span>
                )}
              </div>
            )}
          </div>
        )}

        {/* STRUCTURE TAB */}
        {tab === "structure" && (
          <div>
            <h3 style={{ color: "#f0f0f0" }}>Table Structure</h3>
            {!modifyingStructure ? (
              <div>
                <p style={{ color: "#ccc", marginBottom: "20px" }}>
                  Table <strong>{tableName}</strong> has{" "}
                  {structureColumns.length} column
                  {structureColumns.length !== 1 ? "s" : ""}
                </p>
                {structureColumns.length > 0 ? (
                  <div style={{ overflowX: "auto" }}>
                    <table className="result-table">
                      <thead>
                        <tr>
                          <th>Column Name</th>
                          <th>Type</th>
                          <th>Primary Key</th>
                          <th>Not Null</th>
                          <th>Autoincrement</th>
                          <th>Unique</th>
                          <th>CHECK Constraint</th>
                        </tr>
                      </thead>
                      <tbody>
                        {structureColumns.map((col, idx) => (
                          <tr key={idx}>
                            <td>
                              <strong>{col.name}</strong>
                            </td>
                            <td>{col.type}</td>
                            <td>{col.pk ? "✓" : ""}</td>
                            <td>{col.pk || col.notnull ? "✓" : ""}</td>
                            <td>{col.autoincrement ? "✓" : ""}</td>
                            <td>{col.pk || col.unique ? "✓" : ""}</td>
                            <td
                              style={{
                                fontFamily: "monospace",
                                fontSize: "0.85em",
                                color: checkConstraints[col.name]
                                  ? "#4caf50"
                                  : "#666",
                              }}
                            >
                              {checkConstraints[col.name] || "None"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p style={{ color: "#ccc" }}>
                    No structure information available
                  </p>
                )}
                <div style={{ marginTop: "30px" }}>
                  <button
                    onClick={() => setModifyingStructure(true)}
                    style={{ background: "#9370db" }}
                  >
                    Modify Structure
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <h4 style={{ color: "#f0f0f0" }}>Modify Table Structure</h4>
                <form onSubmit={handleStructureSubmit}>
                  <div style={{ marginBottom: "15px" }}>
                    <label
                      style={{
                        color: "#f0f0f0",
                        display: "block",
                        marginBottom: "5px",
                      }}
                    >
                      Table Name:
                    </label>
                    <input
                      type="text"
                      value={newTableName}
                      onChange={(e) => setNewTableName(e.target.value)}
                      required
                      style={{
                        padding: "8px",
                        border: "1.5px solid #9370db",
                        borderRadius: "5px",
                        background: "rgba(30, 0, 51, 0.5)",
                        color: "#f0f0f0",
                        width: "300px",
                      }}
                    />
                  </div>

                  {/* ✅ SCROLLABLE CONTAINER for columns */}
                  <div
                    style={{
                      marginBottom: "20px",
                      overflowX: "auto",
                      overflowY: "visible",
                      paddingBottom: "10px",
                      maxWidth: "100%",
                    }}
                  >
                    <div
                      style={{
                        minWidth: "1200px", // ✅ Increased for CHECK column
                        display: "flex",
                        flexDirection: "column",
                        gap: "10px",
                      }}
                    >
                      {structureColumns.map((col, idx) => (
                        <div key={col.index || idx}>
                          {/* Main column row */}
                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns:
                                "200px 230px 120px 120px 120px 100px 100px 100px 80px",
                              gap: "10px",
                              alignItems: "center",
                              padding: "10px 15px",
                              background: "rgba(147, 112, 219, 0.1)",
                              borderRadius: "5px",
                              width: "100%",
                              boxSizing: "border-box",
                            }}
                          >
                            {/* Column Name Input */}
                            <input
                              type="text"
                              value={col.name}
                              onChange={(e) =>
                                handleStructureColumnChange(
                                  idx,
                                  "name",
                                  e.target.value
                                )
                              }
                              placeholder="Column Name"
                              required
                              style={{
                                padding: "8px",
                                border: "1.5px solid #9370db",
                                borderRadius: "5px",
                                background: "rgba(30, 0, 51, 0.5)",
                                color: "#f0f0f0",
                                width: "100%",
                                boxSizing: "border-box",
                              }}
                            />

                            {/* Type and Length Combined */}
                            <div
                              style={{
                                display: "flex",
                                gap: "5px",
                                alignItems: "center",
                                width: "100%",
                              }}
                            >
                              <select
                                value={
                                  col.type.includes("(")
                                    ? col.type.split("(")[0].toUpperCase()
                                    : col.type.toUpperCase()
                                }
                                onChange={(e) => {
                                  const baseType = e.target.value;
                                  const requiresLength = [
                                    "VARCHAR",
                                    "CHAR",
                                    "DECIMAL",
                                    "NUMERIC",
                                  ].includes(baseType);

                                  if (requiresLength) {
                                    const currentLength = col.type.includes("(")
                                      ? col.type.match(/\((\d+)\)/)?.[1] ||
                                        "255"
                                      : "255";
                                    handleStructureColumnChange(
                                      idx,
                                      "type",
                                      `${baseType}(${currentLength})`
                                    );
                                  } else {
                                    handleStructureColumnChange(
                                      idx,
                                      "type",
                                      baseType
                                    );
                                  }
                                }}
                                style={{
                                  padding: "8px",
                                  border: "1.5px solid #9370db",
                                  borderRadius: "5px",
                                  background: "rgba(30, 0, 51, 0.9)",
                                  color: "#f0f0f0",
                                  flex: 1,
                                  minWidth: "100px",
                                  boxSizing: "border-box",
                                }}
                              >
                                {types.map((type) => {
                                  const baseType = type.includes("(")
                                    ? type.split("(")[0]
                                    : type;
                                  return (
                                    <option key={baseType} value={baseType}>
                                      {baseType}
                                    </option>
                                  );
                                })}
                              </select>

                              {/* Length input */}
                              {(() => {
                                const baseType = col.type.includes("(")
                                  ? col.type.split("(")[0].toUpperCase()
                                  : col.type.toUpperCase();
                                const needsLength = [
                                  "VARCHAR",
                                  "CHAR",
                                  "DECIMAL",
                                  "NUMERIC",
                                ].includes(baseType);

                                if (needsLength) {
                                  const currentLength = col.type.includes("(")
                                    ? col.type.match(/\((\d+)\)/)?.[1] || ""
                                    : "";

                                  return (
                                    <input
                                      type="text"
                                      value={currentLength}
                                      onChange={(e) => {
                                        const length = e.target.value;
                                        if (
                                          length === "" ||
                                          /^\d+$/.test(length)
                                        ) {
                                          if (length === "") {
                                            handleStructureColumnChange(
                                              idx,
                                              "type",
                                              baseType
                                            );
                                          } else {
                                            handleStructureColumnChange(
                                              idx,
                                              "type",
                                              `${baseType}(${length})`
                                            );
                                          }
                                        }
                                      }}
                                      onBlur={(e) => {
                                        if (e.target.value === "") {
                                          handleStructureColumnChange(
                                            idx,
                                            "type",
                                            `${baseType}(255)`
                                          );
                                        }
                                      }}
                                      placeholder="Len"
                                      style={{
                                        width: "70px",
                                        padding: "8px",
                                        border: "1.5px solid #9370db",
                                        borderRadius: "5px",
                                        background: "rgba(30, 0, 51, 0.5)",
                                        color: "#f0f0f0",
                                        boxSizing: "border-box",
                                      }}
                                    />
                                  );
                                }
                                return null;
                              })()}
                            </div>

                            {/* Primary Key Checkbox */}
                            <label
                              style={{
                                color: "#f0f0f0",
                                display: "flex",
                                alignItems: "center",
                                cursor: "pointer",
                                fontSize: "0.9em",
                                whiteSpace: "nowrap",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={col.pk || false}
                                onChange={(e) =>
                                  handlePKChange(idx, e.target.checked)
                                }
                                style={{ marginRight: "5px" }}
                              />
                              Primary Key
                            </label>

                            {/* Not Null Checkbox */}
                            <label
                              style={{
                                color: "#f0f0f0",
                                display: "flex",
                                alignItems: "center",
                                cursor:
                                  col.pk || col.autoincrement
                                    ? "not-allowed"
                                    : "pointer",
                                opacity: col.pk || col.autoincrement ? 0.6 : 1,
                                fontSize: "0.9em",
                                whiteSpace: "nowrap",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={
                                  col.pk ||
                                  col.notnull ||
                                  col.autoincrement ||
                                  false
                                }
                                onChange={(e) =>
                                  handleStructureColumnChange(
                                    idx,
                                    "notnull",
                                    e.target.checked
                                  )
                                }
                                disabled={col.pk || col.autoincrement}
                                style={{ marginRight: "5px" }}
                              />
                              Not Null
                            </label>

                            {/* Autoincrement Checkbox */}
                            <label
                              style={{
                                color: "#f0f0f0",
                                display: "flex",
                                alignItems: "center",
                                cursor:
                                  (supportsNonPkAutoincrement || col.pk) &&
                                  canSupportAutoincrement(col.type, handlerName)
                                    ? "pointer"
                                    : "not-allowed",
                                opacity:
                                  (supportsNonPkAutoincrement || col.pk) &&
                                  canSupportAutoincrement(col.type, handlerName)
                                    ? 1
                                    : 0.6,
                                fontSize: "0.9em",
                                whiteSpace: "nowrap",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={col.autoincrement || false}
                                onChange={(e) => {
                                  if (
                                    canSupportAutoincrement(
                                      col.type,
                                      handlerName
                                    )
                                  ) {
                                    if (
                                      !supportsNonPkAutoincrement &&
                                      !col.pk
                                    ) {
                                      return;
                                    }
                                    handleStructureColumnChange(
                                      idx,
                                      "autoincrement",
                                      e.target.checked
                                    );
                                  }
                                }}
                                disabled={
                                  (!supportsNonPkAutoincrement && !col.pk) ||
                                  !canSupportAutoincrement(
                                    col.type,
                                    handlerName
                                  )
                                }
                                style={{ marginRight: "5px" }}
                              />
                              Auto Inc
                            </label>

                            {/* Unique Checkbox */}
                            <label
                              style={{
                                color: "#f0f0f0",
                                display: "flex",
                                alignItems: "center",
                                cursor:
                                  col.pk || col.autoincrement
                                    ? "not-allowed"
                                    : "pointer",
                                opacity: col.pk || col.autoincrement ? 0.6 : 1,
                                fontSize: "0.9em",
                                whiteSpace: "nowrap",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={
                                  col.pk ||
                                  col.unique ||
                                  col.autoincrement ||
                                  false
                                }
                                onChange={(e) => {
                                  if (!col.pk && !col.autoincrement) {
                                    handleStructureColumnChange(
                                      idx,
                                      "unique",
                                      e.target.checked
                                    );
                                  }
                                }}
                                disabled={col.pk || col.autoincrement}
                                style={{ marginRight: "5px" }}
                              />
                              Unique
                            </label>

                            {/* ✅ CHECK Constraint Toggle */}
                            <label
                              style={{
                                color: "#f0f0f0",
                                display: "flex",
                                alignItems: "center",
                                cursor: "pointer",
                                fontSize: "0.9em",
                                whiteSpace: "nowrap",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={Boolean(
                                  checkConstraints[col.name] ||
                                    showCheckEditors[col.name]
                                )}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    // Show editor
                                    setShowCheckEditors({
                                      ...showCheckEditors,
                                      [col.name]: true,
                                    });
                                    // Initialize with empty constraint if none exists
                                    if (!checkConstraints[col.name]) {
                                      setCheckConstraints({
                                        ...checkConstraints,
                                        [col.name]: "",
                                      });
                                    }
                                  } else {
                                    // Remove CHECK constraint
                                    const newChecks = { ...checkConstraints };
                                    delete newChecks[col.name];
                                    setCheckConstraints(newChecks);

                                    const newEditors = { ...showCheckEditors };
                                    delete newEditors[col.name];
                                    setShowCheckEditors(newEditors);
                                  }
                                }}
                                style={{ marginRight: "5px" }}
                              />
                              CHECK
                            </label>

                            {/* Delete Button */}
                            <button
                              type="button"
                              onClick={() => handleDeleteStructureColumn(idx)}
                              style={{
                                background: "#dc3545",
                                padding: "6px 12px",
                                fontSize: "0.85em",
                                color: "white",
                                border: "none",
                                borderRadius: "5px",
                                cursor: "pointer",
                                whiteSpace: "nowrap",
                                boxSizing: "border-box",
                              }}
                            >
                              Delete
                            </button>
                          </div>

                          {/* ✅ CHECK Constraint Editor (shown when checkbox is checked) */}
                          {(checkConstraints[col.name] ||
                            showCheckEditors[col.name]) && (
                            <div
                              style={{
                                marginTop: "5px",
                                marginLeft: "15px",
                                padding: "10px",
                                background: "rgba(76, 175, 80, 0.1)",
                                border: "1.5px solid #4caf50",
                                borderRadius: "5px",
                              }}
                            >
                              <div
                                style={{
                                  marginBottom: "5px",
                                  color: "#4caf50",
                                  fontSize: "0.85em",
                                  fontWeight: "bold",
                                }}
                              >
                                CHECK Constraint for {col.name}:
                              </div>
                              <input
                                type="text"
                                value={checkConstraints[col.name] || ""}
                                onChange={(e) => {
                                  setCheckConstraints({
                                    ...checkConstraints,
                                    [col.name]: e.target.value,
                                  });
                                }}
                                placeholder="e.g., age > 0, price BETWEEN 0 AND 1000"
                                style={{
                                  width: "100%",
                                  padding: "8px",
                                  border: "1.5px solid #4caf50",
                                  borderRadius: "5px",
                                  background: "rgba(30, 0, 51, 0.5)",
                                  color: "#f0f0f0",
                                  fontFamily: "monospace",
                                  fontSize: "0.9em",
                                }}
                              />
                              <div
                                style={{
                                  marginTop: "5px",
                                  fontSize: "0.75em",
                                  color: "#ccc",
                                }}
                              >
                                💡 Examples: age {">"} 18, price {">"} 0, status
                                IN ('active', 'pending')
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div
                    style={{ marginTop: "20px", display: "flex", gap: "10px" }}
                  >
                    <button
                      type="button"
                      onClick={handleAddStructureColumn}
                      style={{ background: "#28a745" }}
                    >
                      + Add Column
                    </button>
                    <button type="submit" style={{ background: "#9370db" }}>
                      Save Changes
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setModifyingStructure(false);
                        fetchStructure();
                      }}
                      style={{ background: "#6c757d" }}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            )}
          </div>
        )}

        {/* QUERY TAB */}
        {tab === "query" && (
          <div>
            <h3 style={{ color: "#f0f0f0" }}>Execute SQL Query</h3>
            <p
              style={{ color: "#ccc", fontSize: "0.9em", marginBottom: "15px" }}
            >
              Execute queries including JOINs, GROUP BY, aggregations, and more.
            </p>

            <form onSubmit={handleQuerySubmit}>
              <div style={{ position: "relative" }}>
                <textarea
                  value={queryText}
                  onChange={(e) => {
                    handleAutocompleteChange(e.target.value, (newValue) => {
                      setQueryText(newValue);
                      resetNavigation();
                    });
                  }}
                  onKeyDown={handleQueryKeyDown}
                  onBlur={() => {
                    // Delay to allow click on suggestion
                    setTimeout(() => hideAutocompleteSuggestions(), 200);
                  }}
                  rows={10}
                  cols={120}
                  placeholder={
                    dbType === "sql"
                      ? `Enter SQL query:

Examples:
  SELECT * FROM ${tableName}
  SELECT * FROM ${tableName} WHERE id > 5
  SELECT t1.*, t2.name FROM ${tableName} t1 JOIN other_table t2 ON t1.id = t2.id
  SELECT COUNT(*) FROM ${tableName}
  SELECT AVG(price) FROM products GROUP BY category`
                      : `Enter NoSQL query (JSON format):

Examples:
  {"field": "value"}
  {"price": {"$gt": 100}}
  {"$and": [{"category": "books"}, {"price": {"$lt": 50}}]}`
                  }
                  required
                  style={{
                    width: "100%",
                    padding: "10px",
                    border: "1.5px solid #9370db",
                    borderRadius: "5px",
                    background: "rgba(147, 112, 219, 0.1)",
                    color: "#f0f0f0",
                    fontSize: "14px",
                    fontFamily: "monospace",
                  }}
                />

                {/* Autocomplete Suggestions */}
                {showAutocompleteSuggestions &&
                  autocompleteSuggestions.length > 0 && (
                    <div
                      style={{
                        position: "absolute",
                        top: "100%",
                        left: 0,
                        right: 0,
                        background: "#2a2a2a",
                        border: "1px solid #9370db",
                        borderRadius: "5px",
                        marginTop: "5px",
                        maxHeight: "200px",
                        overflowY: "auto",
                        zIndex: 1000,
                        boxShadow: "0 4px 6px rgba(0, 0, 0, 0.3)",
                      }}
                    >
                      {autocompleteSuggestions.map((suggestion, idx) => (
                        <div
                          key={idx}
                          onClick={() => {
                            selectAutocompleteSuggestion(
                              suggestion,
                              (selected) => {
                                setQueryText(selected);
                                resetNavigation();
                              }
                            );
                          }}
                          style={{
                            padding: "10px",
                            cursor: "pointer",
                            background:
                              idx === autocompleteSelectedIndex
                                ? "#4b0082"
                                : "transparent",
                            color: "#f0f0f0",
                            borderBottom:
                              idx < autocompleteSuggestions.length - 1
                                ? "1px solid #444"
                                : "none",
                            fontSize: "13px",
                            fontFamily: "monospace",
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                          }}
                          onMouseEnter={(e) => {
                            e.target.style.background = "#4b0082";
                          }}
                          onMouseLeave={(e) => {
                            e.target.style.background =
                              idx === autocompleteSelectedIndex
                                ? "#4b0082"
                                : "transparent";
                          }}
                        >
                          {suggestion.length > 100
                            ? suggestion.substring(0, 100) + "..."
                            : suggestion}
                        </div>
                      ))}
                    </div>
                  )}
              </div>

              <div
                style={{
                  fontSize: "12px",
                  color: "#999",
                  marginTop: "4px",
                }}
              >
                💡 Press ↑/↓ to navigate query history
                {sessionQueries.length > 0 &&
                  ` (${sessionQueries.length} queries)`}
                {showAutocompleteSuggestions &&
                  autocompleteSuggestions.length > 0 &&
                  " | Use arrow keys + Enter to select suggestion"}
              </div>

              <br />
              <button
                type="submit"
                style={{ background: "#6a5acd", marginTop: "10px" }}
              >
                Execute Query
              </button>
            </form>

            {queryResult && (
              <div style={{ marginTop: "20px" }}>
                <h3 style={{ color: "#f0f0f0" }}>Query Results</h3>
                {Array.isArray(queryResult) && queryResult.length > 0 ? (
                  queryResult[0] &&
                  typeof queryResult[0] === "object" &&
                  Object.keys(queryResult[0]).length > 0 ? (
                    <div style={{ overflowX: "auto" }}>
                      <table className="result-table">
                        <thead>
                          <tr>
                            {Object.keys(queryResult[0]).map((key) => (
                              <th key={key}>{key}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {queryResult.map((row, idx) => (
                            <tr key={idx}>
                              {Object.values(row).map((value, vidx) => (
                                <td key={vidx}>
                                  {value !== null && value !== undefined
                                    ? typeof value === "object"
                                      ? JSON.stringify(value)
                                      : String(value)
                                    : "NULL"}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p
                      style={{
                        textAlign: "center",
                        fontStyle: "italic",
                        color: "#666",
                      }}
                    >
                      Query executed successfully. No results returned.
                    </p>
                  )
                ) : Array.isArray(queryResult) && queryResult.length === 0 ? (
                  <p
                    style={{
                      textAlign: "center",
                      fontStyle: "italic",
                      color: "#666",
                    }}
                  >
                    Query executed successfully. No results returned.
                  </p>
                ) : typeof queryResult === "object" &&
                  queryResult.rows_affected !== undefined ? (
                  <div
                    style={{
                      padding: "15px",
                      background: "#e8f5e9",
                      borderLeft: "4px solid #4caf50",
                      borderRadius: "5px",
                      color: "#1b5e20",
                    }}
                  >
                    <strong>Rows affected:</strong> {queryResult.rows_affected}
                  </div>
                ) : typeof queryResult === "object" &&
                  (queryResult.status || queryResult.message) ? (
                  <div
                    style={{
                      padding: "15px",
                      background: "#e8f5e9",
                      borderLeft: "4px solid #4caf50",
                      borderRadius: "5px",
                      color: "#1b5e20",
                    }}
                  >
                    {queryResult.status || queryResult.message}
                  </div>
                ) : (
                  <pre
                    style={{
                      background: "rgba(147, 112, 219, 0.1)",
                      padding: "15px",
                      borderRadius: "5px",
                      color: "#f0f0f0",
                      overflowX: "auto",
                    }}
                  >
                    {JSON.stringify(queryResult, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}

        {/* PROCEDURES TAB */}
        {tab === "procedures" && supportsProcedures && (
          <div>
            <h3 style={{ color: "#f0f0f0" }}>
              🔧 Stored Procedures & Functions
            </h3>
            <div style={{ marginBottom: "20px" }}>
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  navigate(`/db/${dbName}/procedures`);
                }}
                style={{ color: "#9370db" }}
              >
                📋 View All Database Procedures →
              </a>
            </div>

            <h4 style={{ color: "#f0f0f0" }}>Create New Procedure</h4>
            <form onSubmit={handleExecuteProcedure}>
              <textarea
                value={procedureCode}
                onChange={(e) => setProcedureCode(e.target.value)}
                rows={15}
                cols={120}
                placeholder={`Example MySQL Stored Procedure:

DELIMITER $$
CREATE PROCEDURE GetTopStudents()
BEGIN
    SELECT name, marks FROM students WHERE marks > 85;
END$$
DELIMITER ;

-- To call the procedure:
CALL GetTopStudents();`}
                style={{
                  width: "100%",
                  padding: "10px",
                  border: "1.5px solid #9370db",
                  borderRadius: "5px",
                  background: "rgba(147, 112, 219, 0.1)",
                  color: "#f0f0f0",
                  fontSize: "14px",
                  fontFamily: "monospace",
                }}
              />
              <br />
              <button
                type="submit"
                style={{ background: "#6a5acd", marginTop: "10px" }}
              >
                ⚙️ Execute Procedure Code
              </button>
            </form>

            {queryResult && (
              <div style={{ marginTop: "20px" }}>
                <h3 style={{ color: "#f0f0f0" }}>Execution Result</h3>
                {Array.isArray(queryResult) && queryResult.length > 0 ? (
                  queryResult[0] &&
                  typeof queryResult[0] === "object" &&
                  Object.keys(queryResult[0]).length > 0 ? (
                    <div style={{ overflowX: "auto" }}>
                      <table className="result-table">
                        <thead>
                          <tr>
                            {Object.keys(queryResult[0]).map((key) => (
                              <th key={key}>{key}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {queryResult.map((row, idx) => (
                            <tr key={idx}>
                              {Object.values(row).map((value, vidx) => (
                                <td key={vidx}>
                                  {value !== null && value !== undefined
                                    ? typeof value === "object"
                                      ? JSON.stringify(value)
                                      : String(value)
                                    : "NULL"}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p
                      style={{
                        textAlign: "center",
                        fontStyle: "italic",
                        color: "#666",
                      }}
                    >
                      Procedure executed successfully. No results returned.
                    </p>
                  )
                ) : typeof queryResult === "object" &&
                  (queryResult.status || queryResult.message) ? (
                  <div
                    style={{
                      padding: "15px",
                      background: "#e8f5e9",
                      borderLeft: "4px solid #4caf50",
                      borderRadius: "5px",
                      color: "#1b5e20",
                    }}
                  >
                    {queryResult.status || queryResult.message}
                  </div>
                ) : (
                  <pre
                    style={{
                      background: "rgba(147, 112, 219, 0.1)",
                      padding: "15px",
                      borderRadius: "5px",
                      color: "#f0f0f0",
                    }}
                  >
                    {JSON.stringify(queryResult, null, 2)}
                  </pre>
                )}
              </div>
            )}

            <h4 style={{ color: "#f0f0f0", marginTop: "30px" }}>
              Existing Procedures & Functions
            </h4>
            {procedures.length > 0 ? (
              <table className="result-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {procedures.map((proc, idx) => (
                    <tr key={idx}>
                      <td>
                        <strong>{proc.name}</strong>
                      </td>
                      <td>{proc.type}</td>
                      <td>{proc.created || "N/A"}</td>
                      <td>
                        <button
                          onClick={() =>
                            handleExecuteSpecificProcedure(proc.name)
                          }
                          style={{
                            background: "#28a745",
                            marginRight: "5px",
                            fontSize: "0.9em",
                          }}
                        >
                          ▶️ Execute
                        </button>
                        <button
                          onClick={() => handleOpenEditProcedure(proc)}
                          style={{
                            background: "#17a2b8",
                            marginRight: "5px",
                            fontSize: "0.9em",
                          }}
                        >
                          ✏️ Edit
                        </button>
                        <button
                          onClick={async () => {
                            try {
                              const response = await axios.get(
                                `/api/table/${dbName}/${tableName}/procedure/${proc.name}/code`
                              );
                              if (response.data.success) {
                                alert(response.data.code);
                              }
                            } catch (err) {
                              alert("Failed to load code");
                            }
                          }}
                          style={{ background: "#6a5acd", marginRight: "5px" }}
                        >
                          📄 View Code
                        </button>
                        <button
                          onClick={async () => {
                            if (
                              !window.confirm(
                                `Delete ${proc.type.toLowerCase()} ${
                                  proc.name
                                }?`
                              )
                            )
                              return;
                            try {
                              const response = await axios.delete(
                                `/api/table/${dbName}/${tableName}/procedures`,
                                {
                                  data: {
                                    procedure_name: proc.name,
                                    is_function: proc.type === "FUNCTION",
                                  },
                                }
                              );
                              if (response.data.success) {
                                setMessage("Procedure dropped successfully");
                                fetchProcedures();
                              }
                            } catch (err) {
                              setError("Failed to drop procedure");
                            }
                          }}
                          style={{ background: "#dc3545" }}
                        >
                          🗑️ Drop
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p
                style={{
                  textAlign: "center",
                  fontStyle: "italic",
                  color: "#666",
                }}
              >
                No procedures or functions exist in this database.
              </p>
            )}
          </div>
        )}

        {/* TRIGGERS TAB */}
        {tab === "triggers" && supportsTriggers && (
          <div>
            <h3 style={{ color: "#f0f0f0" }}>
              Manage Triggers for {tableName}
            </h3>
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                navigate(`/db/${dbName}/triggers`);
              }}
              style={{ color: "#9370db" }}
            >
              View All Database Triggers →
            </a>
            <br />
            <br />

            <h4 style={{ color: "#f0f0f0" }}>Create New Trigger</h4>
            <form onSubmit={handleCreateTrigger}>
              <div style={{ marginBottom: "10px" }}>
                <label style={{ color: "#f0f0f0" }}>Trigger Name:</label>
                <input
                  type="text"
                  value={triggerForm.trigger_name}
                  onChange={(e) =>
                    setTriggerForm({
                      ...triggerForm,
                      trigger_name: e.target.value,
                    })
                  }
                  placeholder={`e.g., auto_timestamp_${tableName}`}
                  required
                  style={{ width: "300px", marginLeft: "10px" }}
                />
              </div>
              <div style={{ marginBottom: "10px" }}>
                <label style={{ color: "#f0f0f0" }}>Timing:</label>
                <select
                  value={triggerForm.trigger_timing}
                  onChange={(e) =>
                    setTriggerForm({
                      ...triggerForm,
                      trigger_timing: e.target.value,
                    })
                  }
                  style={{ marginLeft: "10px" }}
                >
                  <option value="BEFORE">BEFORE</option>
                  <option value="AFTER">AFTER</option>
                </select>
                <label style={{ marginLeft: "20px", color: "#f0f0f0" }}>
                  Event:
                </label>
                <select
                  value={triggerForm.trigger_event}
                  onChange={(e) =>
                    setTriggerForm({
                      ...triggerForm,
                      trigger_event: e.target.value,
                    })
                  }
                  style={{ marginLeft: "10px" }}
                >
                  <option value="INSERT">INSERT</option>
                  <option value="UPDATE">UPDATE</option>
                  <option value="DELETE">DELETE</option>
                </select>
              </div>
              <div style={{ marginBottom: "10px" }}>
                <label style={{ color: "#f0f0f0" }}>Trigger Body:</label>
                <textarea
                  value={triggerForm.trigger_body}
                  onChange={(e) =>
                    setTriggerForm({
                      ...triggerForm,
                      trigger_body: e.target.value,
                    })
                  }
                  rows={8}
                  cols={100}
                  placeholder={`Examples (RETURN is auto-added if missing):

-- Auto-update timestamp on INSERT/UPDATE
NEW.updated_at := NOW();

-- Capitalize text on INSERT
NEW.name := INITCAP(NEW.name);
RAISE NOTICE 'Capitalized: % (id: %)', NEW.name, NEW.id;`}
                  required
                  style={{
                    width: "100%",
                    padding: "10px",
                    border: "1.5px solid #9370db",
                    borderRadius: "5px",
                    background: "rgba(147, 112, 219, 0.1)",
                    color: "#f0f0f0",
                    fontFamily: "monospace",
                  }}
                />
              </div>
              <button type="submit" style={{ background: "#6a5acd" }}>
                Create Trigger
              </button>
            </form>

            <h4 style={{ color: "#f0f0f0", marginTop: "30px" }}>
              Existing Triggers on {tableName}
            </h4>
            {triggers.length > 0 ? (
              <table className="result-table">
                <thead>
                  <tr>
                    <th>Trigger Name</th>
                    <th>Timing/Event</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {triggers.map((trigger, idx) => (
                    <tr key={idx}>
                      <td>{trigger.name}</td>
                      <td>
                        {trigger.timing || "N/A"} {trigger.event || "N/A"}
                      </td>
                      <td>
                        <button
                          onClick={() => handleEditTrigger(trigger)}
                          style={{
                            background: "#17a2b8",
                            marginRight: "5px",
                            color: "white",
                            border: "none",
                            borderRadius: "4px",
                            cursor: "pointer",
                          }}
                        >
                          ✏️ Edit
                        </button>
                        <button
                          onClick={() => handleDeleteTrigger(trigger.name)}
                          style={{ background: "#dc3545" }}
                        >
                          🗑️ Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p
                style={{
                  textAlign: "center",
                  fontStyle: "italic",
                  color: "#666",
                }}
              >
                No triggers exist for this table.
              </p>
            )}
          </div>
        )}

        {/* PL/SQL TAB */}
        {tab === "plsql" && (
          <div>
            <h3 style={{ color: "#f0f0f0" }}>Execute PL/SQL Code</h3>
            <p style={{ color: "#666", fontSize: "0.9em" }}>
              Note: For PostgreSQL, wrap code in DO blocks:{" "}
              <code>DO $$ BEGIN ... END $$;</code>
            </p>
            <form onSubmit={handleExecutePlsql}>
              <textarea
                value={plsqlCode}
                onChange={(e) => setPlsqlCode(e.target.value)}
                rows={15}
                cols={120}
                placeholder={`Example PostgreSQL DO block:
DO $$
BEGIN
    UPDATE ${tableName} SET age = age + 1 WHERE age > 18;
    RAISE NOTICE 'Updated records';
END $$;`}
                required
                style={{
                  width: "100%",
                  padding: "10px",
                  border: "1.5px solid #9370db",
                  borderRadius: "5px",
                  background: "rgba(147, 112, 219, 0.1)",
                  color: "#f0f0f0",
                  fontSize: "14px",
                  fontFamily: "monospace",
                }}
              />
              <br />
              <button
                type="submit"
                style={{ background: "#6a5acd", marginTop: "10px" }}
              >
                Execute
              </button>
            </form>

            {queryResult && (
              <div style={{ marginTop: "20px" }}>
                <h3 style={{ color: "#f0f0f0" }}>Execution Result</h3>
                <pre
                  style={{
                    background: "rgba(147, 112, 219, 0.1)",
                    padding: "15px",
                    borderRadius: "5px",
                    color: "#f0f0f0",
                  }}
                >
                  {JSON.stringify(queryResult, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}

        {/* IMPORT/EXPORT TAB */}
        {tab === "importexport" && (
          <ImportExportTab
            dbName={dbName}
            tableName={tableName}
            isTable={true}
          />
        )}

        {/* CHARTS TAB — FULLY WORKING REACT VERSION */}
        {tab === "charts" && (
          <div>
            {chartData ? (
              <ChartCreator chartData={chartData} chartKeys={chartKeys} />
            ) : loading ? (
              <div style={{ textAlign: "center", padding: "80px 20px" }}>
                <div className="loading" style={{ fontSize: "1.4em" }}>
                  Summoning your data from the void...
                </div>
              </div>
            ) : error ? (
              <div style={{ textAlign: "center", padding: "60px 20px" }}>
                <p style={{ color: "#ff6b6b", fontSize: "1.3em" }}>{error}</p>
                <button
                  onClick={() => fetchChartData()}
                  style={{
                    padding: "12px 30px",
                    background: "#9370db",
                    color: "white",
                    border: "none",
                    borderRadius: "8px",
                    fontWeight: "bold",
                    cursor: "pointer",
                  }}
                >
                  Try Again
                </button>
                <div style={{ marginTop: "20px" }}>
                  <a
                    href={`/dbdragoness/db/${dbName}/table/${tableName}?tab=charts`}
                    style={{ color: "#bb86fc" }}
                  >
                    Or use classic HTML charts →
                  </a>
                </div>
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* INSERT MODAL */}
      {showInsertModal && (
        <InsertRowModal
          columns={columns}
          formData={formData}
          onInputChange={handleInputChange}
          onSubmit={handleInsert}
          onClose={() => setShowInsertModal(false)}
        />
      )}

      {/* UPDATE MODAL */}
      {showUpdateModal && (
        <UpdateRowsModal
          columns={columns}
          updateFormData={updateFormData}
          updateCondition={updateCondition}
          onInputChange={handleUpdateInputChange}
          onConditionChange={setUpdateCondition}
          onSubmit={handleUpdate}
          onClose={() => setShowUpdateModal(false)}
        />
      )}

      {/* DELETE MODAL */}
      {showDeleteModal && (
        <DeleteRowsModal
          deleteCondition={deleteCondition}
          onConditionChange={setDeleteCondition}
          onSubmit={handleDeleteBulk}
          onClose={() => setShowDeleteModal(false)}
        />
      )}

      {showEditProcedureModal && editingProcedure && (
        <EditProcedureModal
          dbName={dbName}
          procedureName={editingProcedure.name}
          procedureType={editingProcedure.type}
          onClose={() => {
            setShowEditProcedureModal(false);
            setEditingProcedure(null);
          }}
          onSuccess={(msg) => {
            setMessage(msg);
            fetchProcedures();
          }}
        />
      )}

      {showEditTriggerModal && editingTrigger && (
        <EditTriggerModal
          dbName={dbName}
          tableName={tableName}
          triggerName={editingTrigger.name}
          onClose={() => {
            setShowEditTriggerModal(false);
            setEditingTrigger(null);
          }}
          onSuccess={(msg) => {
            setMessage(msg);
            fetchTriggers();
          }}
        />
      )}
    </>
  );
}

export default TableDetails;
