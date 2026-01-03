import React, { useState, useEffect } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import Sidebar from "../components/Sidebar";
import CreateTableModal from "../components/CreateTableModal";
import DiagramCreator from "../components/DiagramCreator";
import CreateCollectionModal from "../components/CreateCollectionModal";
import ViewsManager from "../components/ViewsManager";
import PartitionsManager from "../components/PartitionsManager";
import NormalizationWizard from "../components/NormalizationWizard";
import { useQueryHistory } from "../hooks/useQueryHistory";
import { useAutocomplete } from "../hooks/useAutocomplete";
import RenameTableModal from "../components/RenameTableModal";
import TableConnectionCard from "../components/TableConnectionCard";
import ImportExportTab from "../components/ImportExportTab";

function DatabaseDetails() {
  const { dbName } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const [tables, setTables] = useState([]);
  const [dbType, setDbType] = useState("sql");
  const [handlerName, setHandlerName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [allTables, setAllTables] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchTimeout, setSearchTimeout] = useState(null);
  const [page, setPage] = useState(1);
  const [perPage] = useState(10);
  const [totalPages, setTotalPages] = useState(1);
  const [totalTables, setTotalTables] = useState(0);
  const [tab, setTab] = useState(searchParams.get("tab") || "tables");
  const [supportsViews, setSupportsViews] = useState(false);
  const [supportsPartitions, setSupportsPartitions] = useState(false);
  const [showMoreDropdown, setShowMoreDropdown] = useState(false);
  const [renameTableModalOpen, setRenameTableModalOpen] = useState(false);
  const [renameTableName, setRenameTableName] = useState("");
  const [supportsProcedures, setSupportsProcedures] = useState(false);
  const [supportsTriggers, setSupportsTriggers] = useState(false);
  const [supportsPipeline, setSupportsPipeline] = useState(false);
  const [pipelineStages, setPipelineStages] = useState([
    { id: 1, query: "", name: "Stage 1", selected: true },
  ]);
  const [nextStageId, setNextStageId] = useState(2);
  const [pipelineMode, setPipelineMode] = useState("query"); // "query" or "visual"
  const [supportsAggregation, setSupportsAggregation] = useState(false);
  const [pipelineCollection, setPipelineCollection] = useState("");
  const [aggSubTab, setAggSubTab] = useState("visual"); // "visual", "direct", or "pipeline"

  // Aggregation state
  const [aggTable, setAggTable] = useState("");
  const [aggSelectFields, setAggSelectFields] = useState([""]);
  const [aggGroupBy, setAggGroupBy] = useState("");
  const [aggOrderBy, setAggOrderBy] = useState("");
  const [aggOrderDirection, setAggOrderDirection] = useState("ASC");
  const [aggJoinTable, setAggJoinTable] = useState("");
  const [aggJoinOn, setAggJoinOn] = useState("");
  const [aggJoinType, setAggJoinType] = useState("INNER");
  const [aggQueryText, setAggQueryText] = useState("");
  const [aggTableAlias, setAggTableAlias] = useState("");
  const [aggJoinTableAlias, setAggJoinTableAlias] = useState("");
  const [aggResult, setAggResult] = useState(null);
  const [showVisualBuilder, setShowVisualBuilder] = useState(true);

  // Query state
  const [queryText, setQueryText] = useState("");
  const [queryResult, setQueryResult] = useState(null);
  const { sessionQueries, addQuery, navigateHistory, resetNavigation } =
    useQueryHistory("database");

  // Users state
  const [supportsUsers, setSupportsUsers] = useState(false);
  const [users, setUsers] = useState([]);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showCreateCollectionModal, setShowCreateCollectionModal] =
    useState(false);

  useEffect(() => {
    fetchTables();
    checkFeatureSupport();
  }, [dbName, page]);

  useEffect(() => {
    // Fetch data based on active tab
    if (tab === "users") {
      fetchUsers();
    }
  }, [tab]);

  useEffect(() => {
    // Close dropdown when clicking outside
    const handleClickOutside = (e) => {
      if (showMoreDropdown && !e.target.closest(".more-dropdown-container")) {
        setShowMoreDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showMoreDropdown]);

  useEffect(() => {
    if (searchTerm) {
      performSearch(searchTerm);
    }
  }, [page]);

  useEffect(() => {
    // Switch to pipeline tab if it becomes available and we're on visual tab
    if (supportsPipeline && aggSubTab === "visual") {
      setAggSubTab("pipeline");
    }
    // Switch to visual tab if pipeline becomes unavailable and we're on pipeline tab
    if (!supportsPipeline && aggSubTab === "pipeline") {
      setAggSubTab("visual");
    }
  }, [supportsPipeline]);

  const fetchTables = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/api/db/${dbName}/tables`, {
        params: { page, per_page: perPage },
      });

      if (response.data.success) {
        if (response.data.tables) {
          const tbls = response.data.tables;
          setAllTables(tbls);
          setTables(tbls);
          setTotalPages(response.data.total_pages);
          setTotalTables(response.data.total_tables || tbls.length);
        } else if (response.data.collections) {
          const colls = response.data.collections;
          setAllTables(colls);
          setTables(colls);
          setTotalPages(response.data.total_pages);
          setTotalTables(response.data.total_collections || colls.length);
        }
        setDbType(response.data.db_type);
        setHandlerName(response.data.handler);

        // ✅ Check if users management is supported
        checkUsersSupport();
      } else {
        setError(response.data.error || "Failed to fetch tables");
      }
    } catch (err) {
      console.error("Failed to fetch tables:", err);
      window.location.reload(true);
    } finally {
      setLoading(false);
    }
  };

  const handleTableRenameSuccess = (newName) => {
    setMessage(`Table renamed/copied successfully to ${newName}`);
    fetchTables();
    setRenameTableModalOpen(false);
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

  const performSearch = async (term) => {
    setSearching(true);
    try {
      const response = await axios.get(`/api/db/${dbName}/tables/search`, {
        params: { q: term, page, per_page: perPage },
      });

      if (response.data.success) {
        const result = response.data.tables || response.data.collections || [];
        setTables(result);
        setTotalPages(response.data.total_pages);
        setTotalTables(response.data.total);
      }
    } catch (err) {
      console.error("Search error:", err);
    } finally {
      setSearching(false);
    }
  };

  const handleSearchChange = (value) => {
    setSearchTerm(value);

    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }

    const timeout = setTimeout(() => {
      performSearch(value);
    }, 300);

    setSearchTimeout(timeout);
  };

  const handleTableCreated = (newTableName) => {
    setShowCreateModal(false);
    setMessage(`Table ${newTableName} created successfully`);
    fetchTables(); // Refresh table list

    // Navigate to the new table
    setTimeout(() => {
      {
        dbType === "nosql"
          ? navigate(`/db/${dbName}/collection/${newTableName}`)
          : navigate(`/db/${dbName}/table/${newTableName}`);
      }
    }, 500);
  };

  const handleAggregationSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");
    setAggResult(null);

    // Direct Query mode - check aggSubTab instead of showVisualBuilder
    if (aggSubTab === "direct") {
      if (!aggQueryText.trim()) {
        setError("Query cannot be empty");
        return;
      }

      try {
        const endpoint =
          dbType === "nosql"
            ? `/api/db/${dbName}/nosql_query`
            : `/api/db/${dbName}/query`;

        const response = await axios.post(endpoint, {
          query: aggQueryText,
        });

        if (response.data.success) {
          setAggResult(response.data.result);
          setMessage("Query executed successfully");
        } else {
          setError(response.data.error || "Query execution failed");
        }
      } catch (err) {
        setError(
          "Failed to execute query: " +
            (err.response?.data?.error || err.message)
        );
      }
      return; // Exit early for direct query
    }

    // Visual Builder mode - rest of the code stays the same
    if (!aggTable) {
      setError("Please select a table/collection");
      return;
    }

    if (!aggSelectFields.some((f) => f.trim())) {
      setError("Please add at least one field");
      return;
    }

    try {
      const response = await axios.post(`/api/db/${dbName}/aggregation`, {
        table: aggTable,
        table_alias: aggTableAlias || undefined,
        select_fields: aggSelectFields.filter((f) => f.trim()),
        group_by: aggGroupBy || undefined,
        order_by: aggOrderBy || undefined,
        order_direction: aggOrderDirection,
        join_config:
          dbType === "sql" && aggJoinTable
            ? {
                table: aggJoinTable,
                table_alias: aggJoinTableAlias || undefined,
                on: aggJoinOn,
                type: aggJoinType,
              }
            : undefined,
      });

      if (response.data.success) {
        setAggResult(response.data.result);
        setMessage("Aggregation executed successfully");
      } else {
        setError(response.data.error || "Aggregation failed");
      }
    } catch (err) {
      setError(
        "Failed to execute aggregation: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  const addAggSelectField = () => {
    setAggSelectFields([...aggSelectFields, ""]);
  };

  const removeAggSelectField = (index) => {
    setAggSelectFields(aggSelectFields.filter((_, i) => i !== index));
  };

  const updateAggSelectField = (index, value) => {
    const updated = [...aggSelectFields];
    updated[index] = value;
    setAggSelectFields(updated);
  };

  const resetAggregation = () => {
    setAggTable("");
    setAggTableAlias("");
    setAggSelectFields([""]);
    setAggGroupBy("");
    setAggOrderBy("");
    setAggOrderDirection("ASC");
    setAggJoinTable("");
    setAggJoinTableAlias("");
    setAggJoinOn("");
    setAggJoinType("INNER");
    setAggQueryText("");
    setAggResult(null);
    setShowVisualBuilder(true);
  };

  const addPipelineStage = () => {
    setPipelineStages([
      ...pipelineStages,
      {
        id: nextStageId,
        query: "",
        name: `Stage ${nextStageId}`,
        selected: false,
      },
    ]);
    setNextStageId(nextStageId + 1);
  };

  const removePipelineStage = (stageId) => {
    if (pipelineStages.length === 1) return;
    setPipelineStages(pipelineStages.filter((s) => s.id !== stageId));
  };

  const updatePipelineStage = (stageId, field, value) => {
    setPipelineStages(
      pipelineStages.map((s) =>
        s.id === stageId ? { ...s, [field]: value } : s
      )
    );
  };

  const movePipelineStage = (stageId, direction) => {
    const idx = pipelineStages.findIndex((s) => s.id === stageId);
    if (
      (direction === "up" && idx === 0) ||
      (direction === "down" && idx === pipelineStages.length - 1)
    ) {
      return;
    }

    const newStages = [...pipelineStages];
    const targetIdx = direction === "up" ? idx - 1 : idx + 1;
    [newStages[idx], newStages[targetIdx]] = [
      newStages[targetIdx],
      newStages[idx],
    ];
    setPipelineStages(newStages);
  };

  const executePipeline = async (executeMode) => {
    setError("");
    setMessage("");
    setAggResult(null);

    const stagesToExecute =
      executeMode === "all"
        ? pipelineStages
        : pipelineStages.filter((s) => s.selected);

    if (stagesToExecute.length === 0) {
      setError("No stages selected for execution");
      return;
    }

    // Check if any stage is empty
    const emptyStages = stagesToExecute.filter((s) => !s.query.trim());
    if (emptyStages.length > 0) {
      setError(
        `Empty stages found: ${emptyStages.map((s) => s.name).join(", ")}`
      );
      return;
    }

    try {
      // ✅ FIX: Build complete aggregation pipeline
      const pipeline = [];

      for (const stage of stagesToExecute) {
        try {
          // Parse each stage query as JSON
          const stageObj = JSON.parse(stage.query.trim());
          pipeline.push(stageObj);
        } catch (parseErr) {
          setError(
            `Invalid JSON in stage "${stage.name}": ${parseErr.message}`
          );
          return;
        }
      }

      if (!pipelineCollection.trim()) {
        setError("Please enter a collection name to run the pipeline on");
        return;
      }
      const collectionName = pipelineCollection.trim();

      if (!collectionName) {
        setError("Collection name is required for aggregation pipeline");
        return;
      }

      // Build the complete MongoDB aggregation command
      const aggregationCommand = `db.${collectionName}.aggregate(${JSON.stringify(
        pipeline
      )})`;

      console.log("Executing aggregation:", aggregationCommand);

      // Execute the complete pipeline as ONE query
      const response = await axios.post(`/api/db/${dbName}/nosql_query`, {
        query: aggregationCommand,
      });

      if (response.data.success) {
        // Format results to show which stages were executed
        const stageResults = [
          {
            stageName: `Pipeline (${stagesToExecute.length} stages on ${collectionName})`,
            result: response.data.result,
          },
        ];

        setAggResult(stageResults);
        setMessage(
          `Executed ${stagesToExecute.length} pipeline stage(s) on ${collectionName}`
        );
      } else {
        setError(response.data.error || "Pipeline execution failed");
      }
    } catch (err) {
      setError(
        "Pipeline execution failed: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  const checkUsersSupport = async () => {
    try {
      const response = await axios.get(`/api/db/${dbName}/users`);
      if (response.data.success) {
        setSupportsUsers(response.data.supports_users);
      }
    } catch (err) {
      console.error("Failed to check users support:", err);
      setSupportsUsers(false);
    }
  };

  const fetchUsers = async () => {
    try {
      const response = await axios.get(`/api/db/${dbName}/users`);
      if (response.data.success) {
        setUsers(response.data.users || []);
        setSupportsUsers(response.data.supports_users);
      }
    } catch (err) {
      console.error("Failed to fetch users:", err);
      setSupportsUsers(false);
    }
  };

  const checkFeatureSupport = async () => {
    try {
      const capResponse = await axios.get(`/api/db/${dbName}/capabilities`);
      if (capResponse.data.success) {
        setSupportsProcedures(
          capResponse.data.capabilities.supports_procedures || false
        );
        setSupportsTriggers(
          capResponse.data.capabilities.supports_triggers || false
        );
        setSupportsPipeline(
          capResponse.data.capabilities.supports_aggregation_pipeline || false
        );
        setSupportsAggregation(
          capResponse.data.capabilities.supports_aggregation || false
        );

        // âœ… CRITICAL: Check views support from capabilities
        const viewsSupport =
          capResponse.data.capabilities.supports_views || false;
        setSupportsViews(viewsSupport);
        console.log(`Views support for ${dbName}: ${viewsSupport}`);
      }

      // âœ… Check partitions support separately (only for SQL)
      if (dbType === "sql") {
        try {
          const partResponse = await axios.get(
            `/api/db/${dbName}/partitions/support`
          );
          if (partResponse.data.success) {
            const partSupport = partResponse.data.supports_partitions || false;
            setSupportsPartitions(partSupport);
            console.log(`Partitions support for ${dbName}: ${partSupport}`);
          }
        } catch (err) {
          console.error("Failed to check partitions support:", err);
          setSupportsPartitions(false);
        }
      }

      // âœ… Check users support
      checkUsersSupport();
    } catch (err) {
      console.error("Failed to check feature support:", err);
    }
  };

  const handleDeleteTable = async (tableName) => {
    const itemType = dbType === "nosql" ? "collection" : "table";

    if (
      !window.confirm(
        `Are you sure you want to delete ${itemType} ${tableName}?`
      )
    ) {
      return;
    }

    try {
      const response = await axios.post(
        `/api/db/${dbName}/table/${tableName}/delete`
      );
      if (response.data.success) {
        setMessage(`Table ${tableName} deleted successfully`);
        fetchTables();
      } else {
        setError(response.data.error || "Failed to delete table");
      }
    } catch (err) {
      setError(
        "Failed to delete table: " + (err.response?.data?.error || err.message)
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
      // ✅ FIX: Use different route for NoSQL queries
      const endpoint =
        dbType === "nosql"
          ? `/api/db/${dbName}/nosql_query`
          : `/api/db/${dbName}/query`;

      const response = await axios.post(endpoint, {
        query: queryText,
      });

      if (response.data.success) {
        await addQuery(queryText);
        setQueryResult(response.data.result);
        setMessage("Query executed successfully");
      } else {
        setError(response.data.error || "Query execution failed");
      }
    } catch (err) {
      setError(
        "Failed to execute query: " + (err.response?.data?.error || err.message)
      );
    }
  };

  const handleTabChange = (newTab) => {
    setTab(newTab);
    setSearchParams({ tab: newTab });
    setError("");
    setMessage("");
    setQueryResult(null);
  };

  const paginatedTables = tables;

  const clearSearch = () => {
    setSearchTerm("");
    setTables(allTables);
    setTotalPages(Math.ceil(allTables.length / perPage));
    setPage(1);
    fetchTables();
  };

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
          <div className="loading">Loading tables...</div>
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
          <h3 style={{ margin: 0, color: "#f0f0f0" }}>
            {dbType === "nosql" ? "Collections" : "Tables"} in {dbName} (
            {dbType.toUpperCase()})
          </h3>
          <span
            style={{ color: "#ccc", fontStyle: "italic", fontSize: "0.9em" }}
          >
            {tables.length} {dbType === "nosql" ? "collection" : "table"}
            {tables.length !== 1 ? "s" : ""}
          </span>
        </div>

        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("/");
          }}
          style={{ color: "#bb86fc" }}
        >
          ← Back to Home
        </a>
        <br />
        <br />

        <button
          onClick={() => {
            if (dbType === "nosql") {
              setShowCreateCollectionModal(true);
            } else {
              setShowCreateModal(true);
            }
          }}
          style={{
            padding: "10px 20px",
            background: "#9370db",
            color: "white",
            border: "none",
            borderRadius: "5px",
            cursor: "pointer",
            fontSize: "14px",
          }}
        >
          Create New {dbType === "nosql" ? "Collection" : "Table"}
        </button>
        <br />
        <br />

        {showCreateModal && (
          <CreateTableModal
            dbName={dbName}
            onClose={() => setShowCreateModal(false)}
            onSuccess={handleTableCreated}
          />
        )}

        {showCreateCollectionModal && (
          <CreateCollectionModal
            dbName={dbName}
            onClose={() => setShowCreateCollectionModal(false)}
            onSuccess={handleTableCreated}
          />
        )}

        {error && <p className="error">{error}</p>}
        {message && <p className="success">{message}</p>}

        {/* TABS */}
        <div className="tabs">
          <button
            className="tab-button"
            onClick={() => handleTabChange("tables")}
            style={{ background: tab === "tables" ? "#4b0082" : "#9370db" }}
          >
            📋 {dbType === "nosql" ? "Collections" : "Tables"}
          </button>
          <button
            className="tab-button"
            onClick={() => handleTabChange("query")}
            style={{ background: tab === "query" ? "#4b0082" : "#9370db" }}
          >
            🔍 Query
          </button>
          {supportsAggregation && (
            <button
              className="tab-button"
              onClick={() => handleTabChange("aggregation")}
              style={{
                background: tab === "aggregation" ? "#4b0082" : "#9370db",
              }}
            >
              📈 Aggregation
            </button>
          )}
          <button
            className="tab-button"
            onClick={() => handleTabChange("importexport")}
            style={{
              background: tab === "importexport" ? "#4b0082" : "#9370db",
            }}
          >
            📦 Import/Export
          </button>
          <button
            className="tab-button"
            onClick={() => handleTabChange("diagrams")}
            style={{ background: tab === "diagrams" ? "#4b0082" : "#9370db" }}
          >
            📊 Diagrams
          </button>

          {supportsProcedures && (
            <button
              className="tab-button"
              onClick={() => navigate(`/db/${dbName}/procedures`)}
              style={{ background: "#9370db" }}
            >
              🔧 Procedures
            </button>
          )}
          {supportsTriggers && (
            <button
              className="tab-button"
              onClick={() => navigate(`/db/${dbName}/triggers`)}
              style={{ background: "#9370db" }}
            >
              🔥 Triggers
            </button>
          )}

          {/* ✅ More dropdown for SQL databases */}
          {dbType === "sql" && (
            <div
              style={{ position: "relative", display: "inline-block" }}
              className="more-dropdown-container"
            >
              <button
                className="tab-button"
                onClick={() => setShowMoreDropdown(!showMoreDropdown)}
                style={{ background: "#9370db", position: "relative" }}
              >
                ⚙️ More ▼
              </button>
              {showMoreDropdown && (
                <div
                  style={{
                    position: "absolute",
                    top: "100%",
                    left: 0,
                    background: "#2a2a2a",
                    border: "1px solid #9370db",
                    borderRadius: "5px",
                    marginTop: "5px",
                    minWidth: "150px",
                    zIndex: 1000,
                    boxShadow: "0 4px 6px rgba(0, 0, 0, 0.3)",
                  }}
                >
                  {supportsViews && (
                    <button
                      onClick={() => {
                        handleTabChange("views");
                        setShowMoreDropdown(false);
                      }}
                      style={{
                        display: "block",
                        width: "100%",
                        padding: "10px 15px",
                        background: tab === "views" ? "#4b0082" : "transparent",
                        color: "#f0f0f0",
                        border: "none",
                        textAlign: "left",
                        cursor: "pointer",
                        borderBottom: "1px solid #444",
                      }}
                      onMouseEnter={(e) =>
                        (e.target.style.background = "#4b0082")
                      }
                      onMouseLeave={(e) =>
                        (e.target.style.background =
                          tab === "views" ? "#4b0082" : "transparent")
                      }
                    >
                      👁️ Views
                    </button>
                  )}
                  {supportsPartitions && (
                    <button
                      onClick={() => {
                        handleTabChange("partitions");
                        setShowMoreDropdown(false);
                      }}
                      style={{
                        display: "block",
                        width: "100%",
                        padding: "10px 15px",
                        background:
                          tab === "partitions" ? "#4b0082" : "transparent",
                        color: "#f0f0f0",
                        border: "none",
                        textAlign: "left",
                        cursor: "pointer",
                        borderBottom: "1px solid #444",
                      }}
                      onMouseEnter={(e) =>
                        (e.target.style.background = "#4b0082")
                      }
                      onMouseLeave={(e) =>
                        (e.target.style.background =
                          tab === "partitions" ? "#4b0082" : "transparent")
                      }
                    >
                      🗂️ Partitions
                    </button>
                  )}
                  <button
                    onClick={() => {
                      handleTabChange("normalization");
                      setShowMoreDropdown(false);
                    }}
                    style={{
                      display: "block",
                      width: "100%",
                      padding: "10px 15px",
                      background:
                        tab === "normalization" ? "#4b0082" : "transparent",
                      color: "#f0f0f0",
                      border: "none",
                      textAlign: "left",
                      cursor: "pointer",
                      borderBottom: supportsUsers ? "1px solid #444" : "none",
                    }}
                    onMouseEnter={(e) =>
                      (e.target.style.background = "#4b0082")
                    }
                    onMouseLeave={(e) =>
                      (e.target.style.background =
                        tab === "normalization" ? "#4b0082" : "transparent")
                    }
                  >
                    📐 Normalization
                  </button>
                  {supportsUsers && (
                    <button
                      onClick={() => {
                        navigate(`/db/${dbName}/users`);
                        setShowMoreDropdown(false);
                      }}
                      style={{
                        display: "block",
                        width: "100%",
                        padding: "10px 15px",
                        background: "transparent",
                        color: "#f0f0f0",
                        border: "none",
                        textAlign: "left",
                        cursor: "pointer",
                      }}
                      onMouseEnter={(e) =>
                        (e.target.style.background = "#4b0082")
                      }
                      onMouseLeave={(e) =>
                        (e.target.style.background = "transparent")
                      }
                    >
                      👥 Users
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ✅ Users button for NoSQL (shown directly) */}
          {dbType === "nosql" && supportsUsers && (
            <button
              className="tab-button"
              onClick={() => navigate(`/db/${dbName}/users`)}
              style={{ background: "#9370db" }}
            >
              👥 Users
            </button>
          )}
        </div>

        {/* TABLES TAB */}
        {tab === "tables" && (
          <div>
            {/* Search Bar */}
            <div style={{ margin: "20px 0", textAlign: "left" }}>
              <input
                type="text"
                placeholder={`Search ${
                  dbType === "nosql" ? "collections" : "tables"
                } on this page...`}
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
                onClick={clearSearch}
                style={{
                  marginLeft: "10px",
                  padding: "8px 16px",
                  background: "#6c757d",
                  color: "white",
                  border: "none",
                  borderRadius: "5px",
                  cursor: "pointer",
                }}
              >
                Clear
              </button>
              <div
                style={{ marginTop: "8px", fontSize: "14px", color: "#ccc" }}
              >
                {searchTerm &&
                  (searching ? (
                    <span style={{ color: "#6a5acd" }}>🔍 Searching...</span>
                  ) : tables.length === 0 ? (
                    <span style={{ color: "#dc3545" }}>
                      ⚠️ No results found.
                    </span>
                  ) : (
                    <span style={{ color: "#28a745" }}>
                      ✓ {totalTables}{" "}
                      {dbType === "nosql"
                        ? totalTables === 1
                          ? "collection matches"
                          : "collections match"
                        : totalTables === 1
                        ? "table matches"
                        : "tables match"}
                    </span>
                  ))}
              </div>
            </div>

            {/* Tables List */}
            {paginatedTables.length > 0 ? (
              <table className="table-list">
                <thead>
                  <tr>
                    <th>
                      {dbType === "nosql" ? "Collection Name" : "Table Name"}
                    </th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedTables.map((item) => {
                    // ✅ FIX: Handle both SQL (string) and NoSQL (object) formats
                    const tableName =
                      typeof item === "string" ? item : item.name;
                    const docCount =
                      typeof item === "object" && item.count !== undefined
                        ? ` (${item.count} doc${item.count !== 1 ? "s" : ""})`
                        : "";

                    return (
                      <tr key={tableName}>
                        <td>
                          <strong>{tableName}</strong>
                          {dbType === "nosql" && (
                            <span style={{ color: "#999", fontSize: "0.9em" }}>
                              {docCount}
                            </span>
                          )}
                        </td>
                        <td>
                          <button
                            className="view-btn"
                            onClick={() => {
                              if (dbType === "nosql") {
                                navigate(
                                  `/db/${dbName}/collection/${tableName}`
                                );
                              } else {
                                navigate(`/db/${dbName}/table/${tableName}`);
                              }
                            }}
                            style={{ background: "#1e9530" }}
                          >
                            View
                          </button>
                          <button
                            onClick={() => {
                              setRenameTableName(tableName);
                              setRenameTableModalOpen(true);
                            }}
                            style={{ background: "#ff9800" }}
                          >
                            Rename
                          </button>
                          <button
                            onClick={() => {
                              // Scroll to connection info
                              const connSection = document.getElementById(
                                `conn-table-${tableName}`
                              );
                              if (connSection) {
                                connSection.scrollIntoView({
                                  behavior: "smooth",
                                  block: "center",
                                });
                                setTimeout(() => {
                                  const detailsEl =
                                    connSection.querySelector("details");
                                  if (detailsEl) detailsEl.open = true;
                                }, 500);
                              }
                            }}
                            style={{ background: "#17a2b8" }}
                          >
                            Connection Info
                          </button>
                          <button
                            onClick={() => handleDeleteTable(tableName)}
                            style={{ background: "#dc3545" }}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    );
                  })}
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
                No {dbType === "nosql" ? "collections" : "tables"} found.
              </p>
            )}

            {/* Pagination */}
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
                  Page {page} of {totalPages} ({totalTables} total)
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

            {/* Table Connection Strings - Paginated */}
            {paginatedTables.length > 0 && (
              <div style={{ marginTop: "40px" }}>
                <h2>Table Connection Strings</h2>
                <p style={{ color: "#ccc", fontSize: "0.9em" }}>
                  ⚠️ Connection info for accessing specific tables/collections
                </p>
                <div
                  style={{
                    background: "#1e0033e6",
                    padding: "15px",
                    borderRadius: "5px",
                    marginTop: "20px",
                  }}
                >
                  {paginatedTables.map((item) => {
                    const tableName =
                      typeof item === "string" ? item : item.name;
                    return (
                      <TableConnectionCard
                        key={tableName}
                        dbName={dbName}
                        tableName={tableName}
                      />
                    );
                  })}
                </div>
              </div>
            )}

            {/* Pagination */}
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
                  Page {page} of {totalPages} ({totalTables} total)
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

        {/* QUERY TAB */}
        {tab === "query" && (
          <div>
            <h3 style={{ color: "#f0f0f0" }}>
              Execute {dbType.toUpperCase()} Query
            </h3>
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
                    setTimeout(() => hideAutocompleteSuggestions(), 200);
                  }}
                  rows={10}
                  cols={120}
                  placeholder={
                    dbType === "sql"
                      ? `Enter SQL query:

Examples:
  SELECT * FROM table_name
  SELECT * FROM table1 JOIN table2 ON table1.id = table2.id
  SELECT COUNT(*), category FROM products GROUP BY category
  SELECT AVG(price) FROM products WHERE category = 'electronics'`
                      : `Enter NoSQL query (JSON format):

Examples:
  {"category": "electronics"}
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

                {/* ✅ FIX: Check for procedure table results first */}
                {typeof queryResult === "object" &&
                queryResult !== null &&
                !Array.isArray(queryResult) &&
                queryResult.result_type === "table" ? (
                  /* Procedure returned table data */
                  Array.isArray(queryResult.result) &&
                  queryResult.result.length > 0 ? (
                    <>
                      <div style={{ overflowX: "auto" }}>
                        <table className="result-table">
                          <thead>
                            <tr>
                              {Object.keys(queryResult.result[0]).map((key) => (
                                <th key={key}>{key}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {queryResult.result.map((row, idx) => (
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
                      <div
                        style={{
                          padding: "15px",
                          background: "#e8f5e9",
                          borderLeft: "4px solid #4caf50",
                          borderRadius: "5px",
                          color: "#1b5e20",
                          marginTop: "10px",
                        }}
                      >
                        <strong>Rows returned:</strong>{" "}
                        {queryResult.result.length}
                      </div>
                    </>
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
                  queryResult !== null &&
                  !Array.isArray(queryResult) &&
                  queryResult.result_type === "status" ? (
                  /* Procedure status result */
                  <div
                    style={{
                      padding: "15px",
                      background: "#e8f5e9",
                      borderLeft: "4px solid #4caf50",
                      borderRadius: "5px",
                      color: "#1b5e20",
                    }}
                  >
                    {queryResult.result?.status ||
                      `Rows affected: ${queryResult.rows_affected || 0}`}
                  </div>
                ) : (
                  /* Regular query results - keep existing logic */
                  <>
                    {/* ✅ NoSQL FORMAT - Document-style tables */}
                    {dbType === "nosql" &&
                    Array.isArray(queryResult) &&
                    queryResult.length > 0 ? (
                      queryResult.map((doc, idx) => {
                        const primaryKey = Object.keys(doc)[0] || "doc_id";
                        const docId = doc[primaryKey] || "unknown";

                        return (
                          <table
                            key={idx}
                            className="result-table"
                            style={{
                              width: "90%",
                              margin: "25px auto",
                              borderCollapse: "collapse",
                              border: "1px solid #ddd",
                              borderRadius: "10px",
                              overflow: "hidden",
                              boxShadow: "0 4px 8px rgba(0,0,0,0.1)",
                              background: "rgba(30, 0, 51, 0.9)",
                            }}
                          >
                            <caption
                              style={{
                                fontWeight: "bold",
                                padding: "10px",
                                textAlign: "left",
                                background: "rgba(30, 0, 51, 0.95)",
                                color: "white",
                              }}
                            >
                              Document ID: {docId}
                            </caption>
                            <thead>
                              <tr>
                                <th
                                  style={{
                                    border: "1px solid #ddd",
                                    padding: "12px 18px",
                                    background: "rgba(30, 0, 51, 0.9)",
                                    color: "white",
                                    width: "30%",
                                  }}
                                >
                                  Field
                                </th>
                                <th
                                  style={{
                                    border: "1px solid #ddd",
                                    padding: "12px 18px",
                                    background: "rgba(30, 0, 51, 0.9)",
                                    color: "white",
                                  }}
                                >
                                  Value
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr>
                                <td
                                  style={{
                                    border: "1px solid #ddd",
                                    padding: "12px 18px",
                                    background: "rgba(30, 0, 51, 0.9)",
                                    color: "white",
                                    fontWeight: "bold",
                                  }}
                                >
                                  {primaryKey}
                                </td>
                                <td
                                  style={{
                                    border: "1px solid #ddd",
                                    padding: "12px 18px",
                                    background: "rgba(30, 0, 51, 0.9)",
                                    color: "white",
                                  }}
                                >
                                  {docId}
                                </td>
                              </tr>

                              {Object.entries(doc).map(([key, value]) => {
                                if (key === primaryKey) return null;

                                return (
                                  <tr key={key}>
                                    <td
                                      style={{
                                        border: "1px solid #ddd",
                                        padding: "12px 18px",
                                        background: "rgba(30, 0, 51, 0.9)",
                                        color: "white",
                                        fontWeight: "bold",
                                      }}
                                    >
                                      {key}
                                    </td>
                                    <td
                                      style={{
                                        border: "1px solid #ddd",
                                        padding: "12px 18px",
                                        background: "rgba(30, 0, 51, 0.9)",
                                        color: "white",
                                      }}
                                    >
                                      {value !== null && value !== undefined
                                        ? typeof value === "object"
                                          ? JSON.stringify(value)
                                          : String(value)
                                        : "NULL"}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        );
                      })
                    ) : dbType === "nosql" &&
                      Array.isArray(queryResult) &&
                      queryResult.length === 0 ? (
                      <p
                        style={{
                          textAlign: "center",
                          fontStyle: "italic",
                          color: "#666",
                          marginTop: "30px",
                        }}
                      >
                        Query executed successfully. No results returned.
                      </p>
                    ) : dbType === "sql" &&
                      Array.isArray(queryResult) &&
                      queryResult.length > 0 ? (
                      /* ✅ SQL FORMAT - Standard table */
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
                    ) : Array.isArray(queryResult) &&
                      queryResult.length === 0 ? (
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
                        <strong>Rows affected:</strong>{" "}
                        {queryResult.rows_affected}
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
                  </>
                )}
              </div>
            )}
          </div>
        )}

        {/* AGGREGATION TAB */}
        {tab === "aggregation" && (
          <div>
            <h3 style={{ color: "#f0f0f0" }}>
              📈 Aggregation & Complex Queries
            </h3>
            <p
              style={{ color: "#ccc", fontSize: "0.9em", marginBottom: "20px" }}
            >
              Build and execute queries, aggregations, and pipelines
            </p>

            {/* Sub-tab buttons */}
            <div
              style={{
                marginBottom: "20px",
                display: "flex",
                gap: "10px",
                flexWrap: "wrap",
              }}
            >
              {!supportsPipeline && (
                <button
                  onClick={() => setAggSubTab("visual")}
                  style={{
                    padding: "10px 20px",
                    background: aggSubTab === "visual" ? "#4b0082" : "#6c757d",
                    color: "white",
                    border: "none",
                    borderRadius: "5px",
                    cursor: "pointer",
                  }}
                >
                  🎨 Visual Builder
                </button>
              )}
              {supportsPipeline && (
                <button
                  onClick={() => setAggSubTab("pipeline")}
                  style={{
                    padding: "10px 20px",
                    background:
                      aggSubTab === "pipeline" ? "#4b0082" : "#6c757d",
                    color: "white",
                    border: "none",
                    borderRadius: "5px",
                    cursor: "pointer",
                  }}
                >
                  🔗 Pipeline
                </button>
              )}
              <button
                onClick={() => setAggSubTab("direct")}
                style={{
                  padding: "10px 20px",
                  background: aggSubTab === "direct" ? "#4b0082" : "#6c757d",
                  color: "white",
                  border: "none",
                  borderRadius: "5px",
                  cursor: "pointer",
                }}
              >
                📝 Direct Query
              </button>
              <button
                onClick={resetAggregation}
                style={{
                  padding: "10px 20px",
                  background: "#dc3545",
                  color: "white",
                  border: "none",
                  borderRadius: "5px",
                  cursor: "pointer",
                  marginLeft: "auto",
                }}
              >
                🔄 Reset
              </button>
            </div>

            {/* Visual Builder Sub-tab */}
            {aggSubTab === "visual" && !supportsPipeline && (
              <form onSubmit={handleAggregationSubmit}>
                <div
                  style={{
                    background: "rgba(147, 112, 219, 0.1)",
                    padding: "20px",
                    borderRadius: "10px",
                    marginBottom: "20px",
                  }}
                >
                  {/* Table/Collection Selection */}
                  <div style={{ marginBottom: "15px" }}>
                    <label
                      style={{
                        color: "#f0f0f0",
                        display: "block",
                        marginBottom: "5px",
                      }}
                    >
                      {dbType === "nosql" ? "Collection:" : "Table:"}
                    </label>
                    <div
                      style={{
                        display: "flex",
                        gap: "10px",
                        alignItems: "center",
                      }}
                    >
                      <select
                        value={aggTable}
                        onChange={(e) => setAggTable(e.target.value)}
                        required
                        style={{
                          padding: "8px",
                          width: "300px",
                          border: "1.5px solid #9370db",
                          borderRadius: "5px",
                          background: "rgba(30, 0, 51, 0.5)",
                          color: "#f0f0f0",
                        }}
                      >
                        <option value="">
                          Select {dbType === "nosql" ? "collection" : "table"}
                        </option>
                        {tables.map((t) => {
                          const name = typeof t === "string" ? t : t.name;
                          return (
                            <option key={name} value={name}>
                              {name}
                            </option>
                          );
                        })}
                      </select>
                      {dbType === "sql" && (
                        <>
                          <span style={{ color: "#ccc" }}>AS</span>
                          <input
                            type="text"
                            value={aggTableAlias}
                            onChange={(e) => setAggTableAlias(e.target.value)}
                            placeholder="alias (optional)"
                            style={{
                              padding: "8px",
                              width: "150px",
                              border: "1.5px solid #9370db",
                              borderRadius: "5px",
                              background: "rgba(30, 0, 51, 0.5)",
                              color: "#f0f0f0",
                            }}
                          />
                        </>
                      )}
                    </div>
                  </div>

                  {/* Select Fields */}
                  <div style={{ marginBottom: "15px" }}>
                    <label
                      style={{
                        color: "#f0f0f0",
                        display: "block",
                        marginBottom: "5px",
                      }}
                    >
                      Select Fields{" "}
                      {dbType === "nosql"
                        ? "(projection)"
                        : "(use * for all, or functions like COUNT(*), AVG(price))"}{" "}
                      :
                    </label>
                    {aggSelectFields.map((field, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: "flex",
                          gap: "10px",
                          marginBottom: "8px",
                        }}
                      >
                        <input
                          type="text"
                          value={field}
                          onChange={(e) =>
                            updateAggSelectField(idx, e.target.value)
                          }
                          placeholder={
                            dbType === "nosql"
                              ? "e.g., name, email, 1 (to include field)"
                              : "e.g., name, COUNT(*), AVG(price)"
                          }
                          style={{
                            padding: "8px",
                            flex: 1,
                            border: "1.5px solid #9370db",
                            borderRadius: "5px",
                            background: "rgba(30, 0, 51, 0.5)",
                            color: "#f0f0f0",
                          }}
                        />
                        {aggSelectFields.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeAggSelectField(idx)}
                            style={{
                              padding: "8px 12px",
                              background: "#dc3545",
                              color: "white",
                              border: "none",
                              borderRadius: "5px",
                              cursor: "pointer",
                            }}
                          >
                            ✕
                          </button>
                        )}
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={addAggSelectField}
                      style={{
                        padding: "6px 12px",
                        background: "#28a745",
                        color: "white",
                        border: "none",
                        borderRadius: "5px",
                        cursor: "pointer",
                        fontSize: "0.9em",
                      }}
                    >
                      + Add Field
                    </button>
                  </div>

                  {/* GROUP BY */}
                  <div style={{ marginBottom: "15px" }}>
                    <label
                      style={{
                        color: "#f0f0f0",
                        display: "block",
                        marginBottom: "5px",
                      }}
                    >
                      Group By (optional):
                    </label>
                    <input
                      type="text"
                      value={aggGroupBy}
                      onChange={(e) => setAggGroupBy(e.target.value)}
                      placeholder={
                        dbType === "nosql"
                          ? "e.g., $category, $userId"
                          : "e.g., category, user_id"
                      }
                      style={{
                        padding: "8px",
                        width: "300px",
                        border: "1.5px solid #9370db",
                        borderRadius: "5px",
                        background: "rgba(30, 0, 51, 0.5)",
                        color: "#f0f0f0",
                      }}
                    />
                    {dbType === "nosql" && (
                      <div
                        style={{
                          fontSize: "12px",
                          color: "#999",
                          marginTop: "4px",
                        }}
                      >
                        💡 Use $ prefix for field names (e.g., $category)
                      </div>
                    )}
                  </div>

                  {/* ORDER BY */}
                  <div style={{ marginBottom: "15px" }}>
                    <label
                      style={{
                        color: "#f0f0f0",
                        display: "block",
                        marginBottom: "5px",
                      }}
                    >
                      Order By (optional):
                    </label>
                    <div style={{ display: "flex", gap: "10px" }}>
                      <input
                        type="text"
                        value={aggOrderBy}
                        onChange={(e) => setAggOrderBy(e.target.value)}
                        placeholder="e.g., name, count"
                        style={{
                          padding: "8px",
                          flex: 1,
                          maxWidth: "300px",
                          border: "1.5px solid #9370db",
                          borderRadius: "5px",
                          background: "rgba(30, 0, 51, 0.5)",
                          color: "#f0f0f0",
                        }}
                      />
                      <select
                        value={aggOrderDirection}
                        onChange={(e) => setAggOrderDirection(e.target.value)}
                        style={{
                          padding: "8px",
                          border: "1.5px solid #9370db",
                          borderRadius: "5px",
                          background: "rgba(30, 0, 51, 0.5)",
                          color: "#f0f0f0",
                        }}
                      >
                        <option value="ASC">Ascending</option>
                        <option value="DESC">Descending</option>
                      </select>
                    </div>
                  </div>

                  {/* JOIN/LOOKUP (Both SQL and NoSQL) */}
                  <div
                    style={{
                      marginTop: "20px",
                      padding: "15px",
                      background: "rgba(30, 0, 51, 0.3)",
                      borderRadius: "8px",
                    }}
                  >
                    <h4 style={{ color: "#f0f0f0", marginBottom: "10px" }}>
                      {dbType === "nosql" ? "Lookup (Join)" : "JOIN"} (Optional)
                    </h4>

                    <div style={{ marginBottom: "10px" }}>
                      <label
                        style={{
                          color: "#f0f0f0",
                          display: "block",
                          marginBottom: "5px",
                        }}
                      >
                        {dbType === "nosql" ? "From Collection:" : "Join Type:"}
                      </label>
                      {dbType === "sql" ? (
                        <select
                          value={aggJoinType}
                          onChange={(e) => setAggJoinType(e.target.value)}
                          style={{
                            padding: "8px",
                            width: "200px",
                            border: "1.5px solid #9370db",
                            borderRadius: "5px",
                            background: "rgba(30, 0, 51, 0.5)",
                            color: "#f0f0f0",
                          }}
                        >
                          <option value="INNER">INNER JOIN</option>
                          <option value="LEFT">LEFT JOIN</option>
                          <option value="RIGHT">RIGHT JOIN</option>
                        </select>
                      ) : null}
                    </div>

                    <div style={{ marginBottom: "10px" }}>
                      <label
                        style={{
                          color: "#f0f0f0",
                          display: "block",
                          marginBottom: "5px",
                        }}
                      >
                        {dbType === "nosql"
                          ? "Lookup Collection:"
                          : "Join Table:"}
                      </label>
                      <div
                        style={{
                          display: "flex",
                          gap: "10px",
                          alignItems: "center",
                        }}
                      >
                        <select
                          value={aggJoinTable}
                          onChange={(e) => setAggJoinTable(e.target.value)}
                          style={{
                            padding: "8px",
                            width: "300px",
                            border: "1.5px solid #9370db",
                            borderRadius: "5px",
                            background: "rgba(30, 0, 51, 0.5)",
                            color: "#f0f0f0",
                          }}
                        >
                          <option value="">
                            No {dbType === "nosql" ? "lookup" : "join"}
                          </option>
                          {tables.map((t) => {
                            const name = typeof t === "string" ? t : t.name;
                            return (
                              <option key={name} value={name}>
                                {name}
                              </option>
                            );
                          })}
                        </select>
                        {dbType === "sql" && (
                          <>
                            <span style={{ color: "#ccc" }}>AS</span>
                            <input
                              type="text"
                              value={aggJoinTableAlias}
                              onChange={(e) =>
                                setAggJoinTableAlias(e.target.value)
                              }
                              placeholder="alias (optional)"
                              style={{
                                padding: "8px",
                                width: "150px",
                                border: "1.5px solid #9370db",
                                borderRadius: "5px",
                                background: "rgba(30, 0, 51, 0.5)",
                                color: "#f0f0f0",
                              }}
                            />
                          </>
                        )}
                      </div>
                    </div>

                    <div style={{ marginBottom: "10px" }}>
                      <label
                        style={{
                          color: "#f0f0f0",
                          display: "block",
                          marginBottom: "5px",
                        }}
                      >
                        {dbType === "nosql"
                          ? "Local Field:"
                          : "Join ON condition:"}
                      </label>
                      <input
                        type="text"
                        value={aggJoinOn}
                        onChange={(e) => setAggJoinOn(e.target.value)}
                        placeholder={
                          dbType === "nosql"
                            ? "e.g., department"
                            : "e.g., table1.id = table2.user_id"
                        }
                        style={{
                          padding: "8px",
                          width: "400px",
                          border: "1.5px solid #9370db",
                          borderRadius: "5px",
                          background: "rgba(30, 0, 51, 0.5)",
                          color: "#f0f0f0",
                        }}
                      />
                    </div>

                    {dbType === "nosql" && aggJoinTable && (
                      <>
                        <div style={{ marginBottom: "10px" }}>
                          <label
                            style={{
                              color: "#f0f0f0",
                              display: "block",
                              marginBottom: "5px",
                            }}
                          >
                            Foreign Field:
                          </label>
                          <input
                            type="text"
                            value={aggJoinTableAlias}
                            onChange={(e) =>
                              setAggJoinTableAlias(e.target.value)
                            }
                            placeholder="e.g., deptCode"
                            style={{
                              padding: "8px",
                              width: "400px",
                              border: "1.5px solid #9370db",
                              borderRadius: "5px",
                              background: "rgba(30, 0, 51, 0.5)",
                              color: "#f0f0f0",
                            }}
                          />
                        </div>

                        <div style={{ marginBottom: "10px" }}>
                          <label
                            style={{
                              color: "#f0f0f0",
                              display: "block",
                              marginBottom: "5px",
                            }}
                          >
                            Output Array Field Name (as):
                          </label>
                          <input
                            type="text"
                            value={aggJoinType}
                            onChange={(e) => setAggJoinType(e.target.value)}
                            placeholder="e.g., departmentInfo"
                            style={{
                              padding: "8px",
                              width: "400px",
                              border: "1.5px solid #9370db",
                              borderRadius: "5px",
                              background: "rgba(30, 0, 51, 0.5)",
                              color: "#f0f0f0",
                            }}
                          />
                          <div
                            style={{
                              fontSize: "12px",
                              color: "#999",
                              marginTop: "4px",
                            }}
                          >
                            💡 This will create an array field with matched
                            documents
                          </div>
                        </div>
                      </>
                    )}

                    {dbType === "nosql" && (
                      <div
                        style={{
                          fontSize: "12px",
                          color: "#999",
                          marginTop: "10px",
                          lineHeight: "1.6",
                        }}
                      >
                        📖 Example: To join users with departments:
                        <br />
                        - Lookup Collection: departments
                        <br />
                        - Local Field: department (field in users)
                        <br />
                        - Foreign Field: deptCode (field in departments)
                        <br />- Output Array: departmentInfo
                      </div>
                    )}
                  </div>
                </div>

                <button
                  type="submit"
                  style={{
                    padding: "12px 30px",
                    background: "#6a5acd",
                    color: "white",
                    border: "none",
                    borderRadius: "5px",
                    cursor: "pointer",
                    fontWeight: "bold",
                  }}
                >
                  🚀 Execute Aggregation
                </button>
              </form>
            )}

            {/* Pipeline Sub-tab */}
            {aggSubTab === "pipeline" && supportsPipeline && (
              <>
                <div
                  style={{
                    marginBottom: "20px",
                    display: "flex",
                    gap: "10px",
                    flexWrap: "wrap",
                  }}
                >
                  <button
                    onClick={addPipelineStage}
                    style={{
                      padding: "10px 20px",
                      background: "#28a745",
                      color: "white",
                      border: "none",
                      borderRadius: "5px",
                      cursor: "pointer",
                    }}
                  >
                    ➕ Add Stage
                  </button>
                  <button
                    onClick={() => executePipeline("selected")}
                    style={{
                      padding: "10px 20px",
                      background: "#6a5acd",
                      color: "white",
                      border: "none",
                      borderRadius: "5px",
                      cursor: "pointer",
                    }}
                  >
                    ▶️ Execute Selected
                  </button>
                  <button
                    onClick={() => executePipeline("all")}
                    style={{
                      padding: "10px 20px",
                      background: "#4b0082",
                      color: "white",
                      border: "none",
                      borderRadius: "5px",
                      cursor: "pointer",
                    }}
                  >
                    ⏩ Execute All
                  </button>
                </div>

                <div style={{ marginBottom: "20px" }}>
                  <label
                    style={{
                      color: "#f0f0f0",
                      display: "block",
                      marginBottom: "8px",
                      fontWeight: "bold",
                    }}
                  >
                    📂 Collection to run pipeline on:
                  </label>
                  <div
                    style={{
                      display: "flex",
                      gap: "10px",
                      alignItems: "center",
                    }}
                  >
                    <select
                      value={pipelineCollection}
                      onChange={(e) => setPipelineCollection(e.target.value)}
                      style={{
                        padding: "10px",
                        width: "350px",
                        border: "1.5px solid #9370db",
                        borderRadius: "5px",
                        background: "rgba(30, 0, 51, 0.5)",
                        color: "#f0f0f0",
                        fontSize: "14px",
                      }}
                    >
                      <option value="">Select a collection</option>
                      {tables.map((t) => {
                        const name = typeof t === "string" ? t : t.name;
                        return (
                          <option key={name} value={name}>
                            {name}
                          </option>
                        );
                      })}
                    </select>
                    <span style={{ color: "#ccc", fontSize: "0.9em" }}>
                      (required for execution)
                    </span>
                  </div>
                </div>

                {/* Pipeline Stages */}
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "15px",
                  }}
                >
                  {pipelineStages.map((stage, idx) => (
                    <div
                      key={stage.id}
                      style={{
                        background: "rgba(147, 112, 219, 0.1)",
                        padding: "15px",
                        borderRadius: "10px",
                        border: stage.selected
                          ? "2px solid #6a5acd"
                          : "1px solid #9370db",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          marginBottom: "10px",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "10px",
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={stage.selected}
                            onChange={(e) =>
                              updatePipelineStage(
                                stage.id,
                                "selected",
                                e.target.checked
                              )
                            }
                            style={{
                              width: "18px",
                              height: "18px",
                              cursor: "pointer",
                            }}
                          />
                          <input
                            type="text"
                            value={stage.name}
                            onChange={(e) =>
                              updatePipelineStage(
                                stage.id,
                                "name",
                                e.target.value
                              )
                            }
                            style={{
                              padding: "8px",
                              background: "rgba(30, 0, 51, 0.5)",
                              border: "1px solid #9370db",
                              borderRadius: "5px",
                              color: "#f0f0f0",
                              fontWeight: "bold",
                            }}
                          />
                          <span style={{ color: "#999", fontSize: "0.9em" }}>
                            #{idx + 1}
                          </span>
                        </div>

                        <div style={{ display: "flex", gap: "5px" }}>
                          {idx > 0 && (
                            <button
                              onClick={() => movePipelineStage(stage.id, "up")}
                              style={{
                                padding: "5px 10px",
                                background: "#6c757d",
                                color: "white",
                                border: "none",
                                borderRadius: "5px",
                                cursor: "pointer",
                              }}
                            >
                              ⬆️
                            </button>
                          )}
                          {idx < pipelineStages.length - 1 && (
                            <button
                              onClick={() =>
                                movePipelineStage(stage.id, "down")
                              }
                              style={{
                                padding: "5px 10px",
                                background: "#6c757d",
                                color: "white",
                                border: "none",
                                borderRadius: "5px",
                                cursor: "pointer",
                              }}
                            >
                              ⬇️
                            </button>
                          )}
                          {pipelineStages.length > 1 && (
                            <button
                              onClick={() => removePipelineStage(stage.id)}
                              style={{
                                padding: "5px 10px",
                                background: "#dc3545",
                                color: "white",
                                border: "none",
                                borderRadius: "5px",
                                cursor: "pointer",
                              }}
                            >
                              ❌
                            </button>
                          )}
                        </div>
                      </div>

                      <textarea
                        value={stage.query}
                        onChange={(e) =>
                          updatePipelineStage(stage.id, "query", e.target.value)
                        }
                        rows={6}
                        placeholder={`Enter stage query (JSON format):\n\nExample:\n{"$match": {"status": "active"}}\n{"$group": {"_id": "$category", "count": {"$sum": 1}}}`}
                        style={{
                          width: "100%",
                          padding: "10px",
                          border: "1.5px solid #9370db",
                          borderRadius: "5px",
                          background: "rgba(30, 0, 51, 0.5)",
                          color: "#f0f0f0",
                          fontSize: "13px",
                          fontFamily: "monospace",
                        }}
                      />
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Direct Query Sub-tab */}
            {aggSubTab === "direct" && (
              <form onSubmit={handleAggregationSubmit}>
                <textarea
                  value={aggQueryText}
                  onChange={(e) => setAggQueryText(e.target.value)}
                  rows={10}
                  cols={120}
                  placeholder={
                    dbType === "sql"
                      ? `Enter SQL aggregation query:

Examples:
  SELECT category, COUNT(*) as count FROM products GROUP BY category
  SELECT customer_id, AVG(total) FROM orders GROUP BY customer_id ORDER BY AVG(total) DESC
  SELECT p.category, AVG(p.price) FROM products p JOIN categories c ON p.category_id = c.id GROUP BY p.category`
                      : `Enter NoSQL aggregation query (JSON format):

Examples:
  {"table": "products", "pipeline": [{"$group": {"_id": "$category", "count": {"$sum": 1}}}]}
  {"table": "orders", "pipeline": [{"$group": {"_id": "$customer_id", "avg": {"$avg": "$total"}}}]}`
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
                <br />
                <button
                  type="submit"
                  style={{
                    padding: "12px 30px",
                    background: "#6a5acd",
                    color: "white",
                    border: "none",
                    borderRadius: "5px",
                    cursor: "pointer",
                    fontWeight: "bold",
                    marginTop: "10px",
                  }}
                >
                  Execute Query
                </button>
              </form>
            )}

            {/* Results Display - Same for all sub-tabs */}
            {aggResult && (
              <div style={{ marginTop: "30px" }}>
                <h3 style={{ color: "#f0f0f0" }}>Results</h3>

                {supportsPipeline &&
                Array.isArray(aggResult) &&
                aggResult[0]?.stageName ? (
                  /* Pipeline results - show each stage */
                  aggResult.map((stageResult, stageIdx) => (
                    <div key={stageIdx} style={{ marginBottom: "30px" }}>
                      <h4 style={{ color: "#6a5acd", marginBottom: "15px" }}>
                        📊 {stageResult.stageName}
                      </h4>
                      {stageResult.error ? (
                        <div
                          style={{
                            padding: "15px",
                            background: "#ffebee",
                            borderLeft: "4px solid #f44336",
                            borderRadius: "5px",
                            color: "#c62828",
                          }}
                        >
                          ❌ <strong>Error:</strong> {stageResult.error}
                        </div>
                      ) : stageResult.result &&
                        Array.isArray(stageResult.result) &&
                        stageResult.result.length > 0 ? (
                        stageResult.result.map((doc, idx) => {
                          const primaryKey = Object.keys(doc)[0] || "doc_id";
                          const docId = doc[primaryKey] || "unknown";

                          return (
                            <table
                              key={idx}
                              className="result-table"
                              style={{
                                width: "90%",
                                margin: "25px auto",
                                borderCollapse: "collapse",
                                border: "1px solid #ddd",
                                borderRadius: "10px",
                                overflow: "hidden",
                                boxShadow: "0 4px 8px rgba(0,0,0,0.1)",
                                background: "rgba(30, 0, 51, 0.9)",
                              }}
                            >
                              <caption
                                style={{
                                  fontWeight: "bold",
                                  padding: "10px",
                                  textAlign: "left",
                                  background: "rgba(30, 0, 51, 0.95)",
                                  color: "white",
                                }}
                              >
                                Document ID: {docId}
                              </caption>
                              <thead>
                                <tr>
                                  <th
                                    style={{
                                      border: "1px solid #ddd",
                                      padding: "12px 18px",
                                      background: "rgba(30, 0, 51, 0.9)",
                                      color: "white",
                                      width: "30%",
                                    }}
                                  >
                                    Field
                                  </th>
                                  <th
                                    style={{
                                      border: "1px solid #ddd",
                                      padding: "12px 18px",
                                      background: "rgba(30, 0, 51, 0.9)",
                                      color: "white",
                                    }}
                                  >
                                    Value
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                <tr>
                                  <td
                                    style={{
                                      border: "1px solid #ddd",
                                      padding: "12px 18px",
                                      background: "rgba(30, 0, 51, 0.9)",
                                      color: "white",
                                      fontWeight: "bold",
                                    }}
                                  >
                                    {primaryKey}
                                  </td>
                                  <td
                                    style={{
                                      border: "1px solid #ddd",
                                      padding: "12px 18px",
                                      background: "rgba(30, 0, 51, 0.9)",
                                      color: "white",
                                    }}
                                  >
                                    {docId}
                                  </td>
                                </tr>

                                {Object.entries(doc).map(([key, value]) => {
                                  if (key === primaryKey) return null;

                                  return (
                                    <tr key={key}>
                                      <td
                                        style={{
                                          border: "1px solid #ddd",
                                          padding: "12px 18px",
                                          background: "rgba(30, 0, 51, 0.9)",
                                          color: "white",
                                          fontWeight: "bold",
                                        }}
                                      >
                                        {key}
                                      </td>
                                      <td
                                        style={{
                                          border: "1px solid #ddd",
                                          padding: "12px 18px",
                                          background: "rgba(30, 0, 51, 0.9)",
                                          color: "white",
                                        }}
                                      >
                                        {value !== null && value !== undefined
                                          ? typeof value === "object"
                                            ? JSON.stringify(value)
                                            : String(value)
                                          : "NULL"}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          );
                        })
                      ) : (
                        <p
                          style={{
                            textAlign: "center",
                            fontStyle: "italic",
                            color: "#666",
                          }}
                        >
                          Stage executed successfully. No results returned.
                        </p>
                      )}
                    </div>
                  ))
                ) : dbType === "nosql" &&
                  Array.isArray(aggResult) &&
                  aggResult.length > 0 ? (
                  aggResult.map((doc, idx) => {
                    const primaryKey = Object.keys(doc)[0] || "doc_id";
                    const docId = doc[primaryKey] || "unknown";

                    return (
                      <table
                        key={idx}
                        className="result-table"
                        style={{
                          width: "90%",
                          margin: "25px auto",
                          borderCollapse: "collapse",
                          border: "1px solid #ddd",
                          borderRadius: "10px",
                          overflow: "hidden",
                          boxShadow: "0 4px 8px rgba(0,0,0,0.1)",
                          background: "rgba(30, 0, 51, 0.9)",
                        }}
                      >
                        <caption
                          style={{
                            fontWeight: "bold",
                            padding: "10px",
                            textAlign: "left",
                            background: "rgba(30, 0, 51, 0.95)",
                            color: "white",
                          }}
                        >
                          Document ID: {docId}
                        </caption>
                        <thead>
                          <tr>
                            <th
                              style={{
                                border: "1px solid #ddd",
                                padding: "12px 18px",
                                background: "rgba(30, 0, 51, 0.9)",
                                color: "white",
                                width: "30%",
                              }}
                            >
                              Field
                            </th>
                            <th
                              style={{
                                border: "1px solid #ddd",
                                padding: "12px 18px",
                                background: "rgba(30, 0, 51, 0.9)",
                                color: "white",
                              }}
                            >
                              Value
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td
                              style={{
                                border: "1px solid #ddd",
                                padding: "12px 18px",
                                background: "rgba(30, 0, 51, 0.9)",
                                color: "white",
                                fontWeight: "bold",
                              }}
                            >
                              {primaryKey}
                            </td>
                            <td
                              style={{
                                border: "1px solid #ddd",
                                padding: "12px 18px",
                                background: "rgba(30, 0, 51, 0.9)",
                                color: "white",
                              }}
                            >
                              {docId}
                            </td>
                          </tr>

                          {Object.entries(doc).map(([key, value]) => {
                            if (key === primaryKey) return null;

                            return (
                              <tr key={key}>
                                <td
                                  style={{
                                    border: "1px solid #ddd",
                                    padding: "12px 18px",
                                    background: "rgba(30, 0, 51, 0.9)",
                                    color: "white",
                                    fontWeight: "bold",
                                  }}
                                >
                                  {key}
                                </td>
                                <td
                                  style={{
                                    border: "1px solid #ddd",
                                    padding: "12px 18px",
                                    background: "rgba(30, 0, 51, 0.9)",
                                    color: "white",
                                  }}
                                >
                                  {value !== null && value !== undefined
                                    ? typeof value === "object"
                                      ? JSON.stringify(value)
                                      : String(value)
                                    : "NULL"}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    );
                  })
                ) : dbType === "sql" &&
                  Array.isArray(aggResult) &&
                  aggResult.length > 0 ? (
                  aggResult[0] &&
                  typeof aggResult[0] === "object" &&
                  Object.keys(aggResult[0]).length > 0 ? (
                    <div style={{ overflowX: "auto" }}>
                      <table className="result-table">
                        <thead>
                          <tr>
                            {Object.keys(aggResult[0]).map((key) => (
                              <th key={key}>{key}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {aggResult.map((row, idx) => (
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
                ) : Array.isArray(aggResult) && aggResult.length === 0 ? (
                  <p
                    style={{
                      textAlign: "center",
                      fontStyle: "italic",
                      color: "#666",
                    }}
                  >
                    Query executed successfully. No results returned.
                  </p>
                ) : typeof aggResult === "object" &&
                  aggResult.rows_affected !== undefined ? (
                  <div
                    style={{
                      padding: "15px",
                      background: "#e8f5e9",
                      borderLeft: "4px solid #4caf50",
                      borderRadius: "5px",
                      color: "#1b5e20",
                    }}
                  >
                    <strong>Rows affected:</strong> {aggResult.rows_affected}
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
                    {JSON.stringify(aggResult, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}

        {/* IMPORT/EXPORT TAB */}
        {tab === "importexport" && (
          <ImportExportTab dbName={dbName} tableName={null} isTable={false} />
        )}

        {/* DIAGRAMS TAB */}
        {tab === "diagrams" && (
          <DiagramCreator dbName={dbName} dbType={dbType} />
        )}

        {/* VIEWS TAB */}
        {tab === "views" && <ViewsManager dbName={dbName} />}

        {/* PARTITIONS TAB */}
        {tab === "partitions" && (
          <PartitionsManager dbName={dbName} tables={tables} />
        )}

        {/* NORMALIZATION TAB */}
        {tab === "normalization" && <NormalizationWizard dbName={dbName} />}
      </div>

      {renameTableModalOpen && (
        <RenameTableModal
          dbName={dbName}
          tableName={renameTableName}
          onClose={() => setRenameTableModalOpen(false)}
          onSuccess={handleTableRenameSuccess}
        />
      )}
    </>
  );
}

export default DatabaseDetails;
