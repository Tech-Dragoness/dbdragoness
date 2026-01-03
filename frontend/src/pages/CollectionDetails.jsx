import React, { useState, useEffect } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import Sidebar from "../components/Sidebar";
import AddDocumentModal from "../components/AddDocumentModal";
import ModifyDocumentModal from "../components/ModifyDocumentModal";
import ValidationRulesTab from "../components/ValidationRulesTab";
import ChartCreator from "../components/ChartCreator";
import { useQueryHistory } from "../hooks/useQueryHistory";
import { useAutocomplete } from "../hooks/useAutocomplete";
import ImportExportTab from "../components/ImportExportTab";

function CollectionDetails() {
  const { dbName, collectionName } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [documents, setDocuments] = useState([]);
  const [keys, setKeys] = useState([]);
  const [primaryKey, setPrimaryKey] = useState("doc_id");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [tab, setTab] = useState(searchParams.get("tab") || "data");
  const [totalDocs, setTotalDocs] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [supportsValidation, setSupportsValidation] = useState(false);

  // Query state
  const [queryText, setQueryText] = useState("");
  const [queryResult, setQueryResult] = useState(null);
  const { sessionQueries, addQuery, navigateHistory, resetNavigation } =
    useQueryHistory("collection");

  // Modal state
  const [showAddModal, setShowAddModal] = useState(false);
  const [showModifyModal, setShowModifyModal] = useState(false);
  const [currentDoc, setCurrentDoc] = useState(null);

  // Search/Filter state
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedFields, setSelectedFields] = useState(new Set());
  const [showFilterMenu, setShowFilterMenu] = useState(false);
  const [allDocuments, setAllDocuments] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchTimeout, setSearchTimeout] = useState(null);

  // Charts state
  const [chartData, setChartData] = useState(null);
  const [chartKeys, setChartKeys] = useState([]);

  useEffect(() => {
    if (searchTerm) {
      performSearch(searchTerm, selectedFields);
    }
  }, [page]);

  useEffect(() => {
    if (searchTerm) {
      performSearch(searchTerm, selectedFields);
    }
  }, [page]);

  useEffect(() => {
    const checkValidationSupport = async () => {
      try {
        const response = await axios.get(`/api/db/${dbName}/capabilities`);

        if (response.data.success) {
          setSupportsValidation(
            response.data.capabilities.supports_check_constraints || false
          );
        }
      } catch (error) {
        console.error("Failed to check validation support:", error);
        setSupportsValidation(false);
      }
    };

    checkValidationSupport();
  }, [dbName]);

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

  const performSearch = async (term, fields) => {
    setSearching(true);
    try {
      const fieldsParam = fields.size > 0 ? Array.from(fields).join(",") : "";
      const response = await axios.get(
        `/api/collection/${dbName}/${collectionName}/search`,
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
        setDocuments(response.data.documents);
        setTotalDocs(response.data.total);
        setTotalPages(response.data.total_pages);
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

    if (searchTerm) {
      performSearch(searchTerm, newSelected);
    }
  };

  const openModifyModal = (doc) => {
    setCurrentDoc(doc);
    setShowModifyModal(true);
  };

  useEffect(() => {
    fetchCollectionData();
  }, [dbName, collectionName, page]);

  useEffect(() => {
    if (tab === "charts") {
      fetchChartData();
    }
  }, [tab]);

  const fetchCollectionData = async () => {
    try {
      setLoading(true);
      const response = await axios.get(
        `/api/collection/${dbName}/${collectionName}`,
        {
          params: { page, per_page: perPage },
        }
      );

      if (response.data.success) {
        setDocuments(response.data.documents || []);
        setAllDocuments(response.data.documents || []);
        setKeys(response.data.keys || []);
        setPrimaryKey(response.data.primary_key || "doc_id");
        setTotalDocs(response.data.total_docs || 0);
        setTotalPages(response.data.total_pages || 1);
      } else {
        setError(response.data.error || "Failed to fetch collection data");
      }
    } catch (err) {
      console.error("Failed to fetch collection:", err);
      window.location.reload(true);
    } finally {
      setLoading(false);
    }
  };

  const fetchChartData = async () => {
    try {
      setLoading(true);
      const response = await axios.get(
        `/api/collection/${dbName}/${collectionName}/chart_data`
      );

      if (response.data.success) {
        // Filter out duplicate ID fields (keep only primary key)
        const cleanedData = response.data.data.map((doc) => {
          const clean = {};

          // Add primary key first
          if (primaryKey && doc[primaryKey] !== undefined) {
            clean[primaryKey] = doc[primaryKey];
          }

          // Add other fields (skip alternate ID fields)
          Object.entries(doc).forEach(([key, value]) => {
            if (key !== primaryKey && !["_id", "doc_id"].includes(key)) {
              clean[key] = value;
            }
          });

          return clean;
        });

        // Get unique keys (excluding duplicate IDs)
        const uniqueKeys = [
          ...new Set(cleanedData.flatMap((doc) => Object.keys(doc))),
        ];

        setChartData(cleanedData);
        setChartKeys(uniqueKeys);
      } else {
        setError(response.data.error || "Failed to load chart data");
      }
    } catch (err) {
      console.error("Failed to fetch chart data:", err);
      setError("Failed to load chart data");
    } finally {
      setLoading(false);
    }
  };

  const handleAddSuccess = () => {
    setShowAddModal(false);
    setMessage("Document added successfully");
    fetchCollectionData();
  };

  const handleModifySuccess = () => {
    setShowModifyModal(false);
    setMessage("Document updated successfully");
    fetchCollectionData();
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
        `/api/collection/${dbName}/${collectionName}/query`,
        {
          query: queryText,
        }
      );

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

  if (loading && tab !== "charts") {
    return (
      <>
        <Sidebar dbType="nosql" handlerName="TinyDB" />
        <div className="center">
          <div className="loading">Loading collection...</div>
        </div>
      </>
    );
  }

  return (
    <>
      <Sidebar dbType="nosql" handlerName="TinyDB" />
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
            Collection: {collectionName} in {dbName}
          </h2>
          <span
            style={{ color: "#ccc", fontStyle: "italic", fontSize: "0.9em" }}
          >
            {totalDocs} document{totalDocs !== 1 ? "s" : ""}
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
          ← Back to Collections
        </a>
        <br />
        <br />

        {error && <p className="error">{error}</p>}
        {message && <p className="success">{message}</p>}

        {/* TABS */}
        <div className="tabs">
          <button
            className="tab-button"
            onClick={() => handleTabChange("data")}
            style={{ background: tab === "data" ? "#4b0082" : "#9370db" }}
          >
            📄 Documents
          </button>
          <button
            className="tab-button"
            onClick={() => handleTabChange("query")}
            style={{ background: tab === "query" ? "#4b0082" : "#9370db" }}
          >
            🔍 Query
          </button>
          {supportsValidation && (
            <button
              className="tab-button"
              onClick={() => handleTabChange("validation")}
              style={{
                background: tab === "validation" ? "#4b0082" : "#9370db",
              }}
            >
              ✓ Validation Rules
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
            onClick={() => handleTabChange("charts")}
            style={{ background: tab === "charts" ? "#4b0082" : "#9370db" }}
          >
            📊 Charts
          </button>
        </div>

        {/* DATA TAB */}
        {tab === "data" && (
          <div>
            {/* SEARCH BAR WITH FILTERS */}
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
                  setDocuments(allDocuments);
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
                  {keys.map((key) => (
                    <div key={key} style={{ margin: "8px 0" }}>
                      <label
                        style={{
                          cursor: "pointer",
                          display: "block",
                          padding: "4px 0",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={selectedFields.has(key)}
                          onChange={(e) => toggleField(key, e.target.checked)}
                          style={{ marginRight: "10px" }}
                        />
                        <span>{key}</span>
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
                  ) : documents.length === 0 ? (
                    <span style={{ color: "#dc3545" }}>
                      ⚠️ No results found.
                    </span>
                  ) : (
                    <span style={{ color: "#28a745" }}>
                      ✓ {totalDocs} document{totalDocs !== 1 ? "s" : ""} match
                    </span>
                  )}
                </div>
              )}
            </div>

            <button
              onClick={() => setShowAddModal(true)}
              style={{
                display: "inline-block",
                padding: "10px 20px",
                background: "#6a5acd",
                color: "white",
                borderRadius: "5px",
                border: "none",
                cursor: "pointer",
                fontWeight: "bold",
                marginBottom: "20px",
              }}
            >
              Add Document
            </button>

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
                  Page {page} of {totalPages} ({totalDocs} total)
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

            {documents.length > 0 ? (
              <>
                {documents.map((doc, idx) => {
                  const docId = doc[primaryKey] || "unknown";

                  return (
                    <table
                      key={idx}
                      style={{
                        width: "90%",
                        margin: "20px auto",
                        borderCollapse: "collapse",
                        border: "1px solid #999",
                        boxShadow: "0 0 6px rgba(0,0,0,0.1)",
                      }}
                    >
                      <caption
                        style={{
                          fontWeight: "bold",
                          padding: "8px",
                          textAlign: "left",
                          color: "#f0f0f0",
                        }}
                      >
                        Document ID: {docId}
                      </caption>
                      <thead>
                        <tr>
                          <th
                            style={{
                              border: "1px solid #999",
                              padding: "8px",
                              background: "rgba(30, 0, 51, 0.9)",
                              color: "white",
                            }}
                          >
                            Key
                          </th>
                          <th
                            style={{
                              border: "1px solid #999",
                              padding: "8px",
                              background: "rgba(30, 0, 51, 0.9)",
                              color: "white",
                            }}
                          >
                            Value
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {/* Primary key row */}
                        <tr>
                          <td
                            style={{
                              border: "1px solid #999",
                              padding: "8px",
                              fontWeight: "bold",
                              background: "rgba(30, 0, 51, 0.9)",
                              color: "white",
                            }}
                          >
                            {primaryKey}
                          </td>
                          <td
                            style={{
                              border: "1px solid #999",
                              padding: "8px",
                              background: "rgba(30, 0, 51, 0.9)",
                              color: "white",
                            }}
                          >
                            {docId}
                          </td>
                        </tr>

                        {/* Other fields */}
                        {Object.entries(doc).map(([key, value]) => {
                          if (key === primaryKey) return null;

                          return (
                            <tr key={key}>
                              <td
                                style={{
                                  border: "1px solid #999",
                                  padding: "8px",
                                  background: "rgba(30, 0, 51, 0.9)",
                                  color: "white",
                                }}
                              >
                                {key}
                              </td>
                              <td
                                style={{
                                  border: "1px solid #999",
                                  padding: "8px",
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

                        {/* Actions row */}
                        <tr>
                          <td
                            colSpan="2"
                            style={{
                              textAlign: "center",
                              borderTop: "1px solid #999",
                              padding: "10px",
                              background: "rgba(30, 0, 51, 0.9)",
                            }}
                          >
                            <button
                              onClick={() => {
                                openModifyModal(doc);
                              }}
                              style={{
                                background: "#1e9530",
                                color: "white",
                                border: "none",
                                borderRadius: "4px",
                                padding: "6px 12px",
                                cursor: "pointer",
                                marginRight: "10px",
                              }}
                            >
                              Modify
                            </button>
                            <button
                              onClick={async () => {
                                if (
                                  !window.confirm(
                                    "Are you sure you want to delete this document? This cannot be undone."
                                  )
                                )
                                  return;

                                try {
                                  const docId = doc[primaryKey];
                                  await axios.post(
                                    `/api/collection/${dbName}/${collectionName}/document/${docId}/delete`
                                  );
                                  setMessage("Document deleted successfully");
                                  fetchCollectionData();
                                } catch (err) {
                                  setError(
                                    "Failed to delete: " +
                                      (err.response?.data?.error || err.message)
                                  );
                                }
                              }}
                              style={{
                                background: "#dc3545",
                                color: "white",
                                border: "none",
                                borderRadius: "6px",
                                padding: "8px 16px",
                                cursor: "pointer",
                                fontWeight: "bold",
                              }}
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  );
                })}
              </>
            ) : (
              <p
                style={{
                  color: "#f0f0f0",
                  textAlign: "center",
                  marginTop: "30px",
                }}
              >
                {searchTerm
                  ? "No documents match your search."
                  : "No documents in this collection."}
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
                  Page {page} of {totalPages} ({totalDocs} total)
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
            <h3 style={{ color: "#f0f0f0" }}>Execute NoSQL Query</h3>
            <p
              style={{ color: "#ccc", fontSize: "0.9em", marginBottom: "15px" }}
            >
              Enter TinyDB query JSON format
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
                  placeholder={`Enter NoSQL query (JSON format):

Examples:
  {"table": "${collectionName}", "condition": {}}
  {"table": "${collectionName}", "condition": {"age": {"$gt": 30}}}
  {"table": "${collectionName}", "condition": {"name": "Alice"}}`}
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
                style={{
                  background: "#6a5acd",
                  marginTop: "10px",
                  padding: "10px 20px",
                  color: "white",
                  border: "none",
                  borderRadius: "5px",
                  cursor: "pointer",
                }}
              >
                Execute Query
              </button>
            </form>

            {queryResult && (
              <div style={{ marginTop: "20px" }}>
                <h3 style={{ color: "#f0f0f0" }}>Query Results</h3>
                {Array.isArray(queryResult) && queryResult.length > 0 ? (
                  queryResult.map((doc, idx) => {
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
                          {/* Primary key first */}
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

                          {/* Other fields */}
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
                ) : Array.isArray(queryResult) && queryResult.length === 0 ? (
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

        {/* IMPORT/EXPORT TAB */}
        {tab === "importexport" && (
          <ImportExportTab
            dbName={dbName}
            tableName={collectionName}
            isTable={true}
          />
        )}

        {/* CHARTS TAB */}
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
              </div>
            ) : null}
          </div>
        )}

        {/* VALIDATION TAB */}
        {tab === "validation" && (
          <ValidationRulesTab
            dbName={dbName}
            collectionName={collectionName}
            keys={keys}
            onSuccess={() => {
              setMessage("Validation rules applied successfully");
              fetchCollectionData();
            }}
            onError={(err) => setError(err)}
          />
        )}
      </div>

      {showAddModal && (
        <AddDocumentModal
          dbName={dbName}
          collectionName={collectionName}
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          onSuccess={handleAddSuccess}
        />
      )}

      {showModifyModal && currentDoc && (
        <ModifyDocumentModal
          dbName={dbName}
          collectionName={collectionName}
          document={currentDoc}
          primaryKey={primaryKey}
          onClose={() => {
            setShowModifyModal(false);
            setCurrentDoc(null);
          }}
          onSuccess={handleModifySuccess}
        />
      )}
    </>
  );
}

export default CollectionDetails;
