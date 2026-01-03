import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import Sidebar from "../components/Sidebar";
import { useQueryHistory } from "../hooks/useQueryHistory";
import { useAutocomplete } from "../hooks/useAutocomplete";

function GlobalQuery() {
  const navigate = useNavigate();

  const [dbType, setDbType] = useState("sql");
  const [handlerName, setHandlerName] = useState("");
  const [currentDb, setCurrentDb] = useState(null);
  const [queryText, setQueryText] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [ghostText, setGhostText] = useState("");
  const textareaRef = useRef(null);
  const autocompleteTimeout = useRef(null);

  const { sessionQueries, addQuery, navigateHistory, resetNavigation } =
    useQueryHistory("global");

  const handleQueryChange = (e) => {
    const newQuery = e.target.value;
    handleAutocompleteChange(newQuery, (value) => {
      setQueryText(value);
      resetNavigation();
    });
  };

  const fetchSuggestion = async (query, cursorPosition) => {
    if (!query.trim()) {
      setGhostText("");
      return;
    }

    try {
      const response = await axios.post("/api/autocomplete", {
        query,
        cursor_position: cursorPosition,
      });

      if (response.data.success && response.data.suggestion) {
        setGhostText(response.data.suggestion);
      } else {
        setGhostText("");
      }
    } catch (err) {
      console.error("Autocomplete error:", err);
      setGhostText("");
    }
  };

  const handleKeyDown = (e) => {
    // First, try autocomplete
    const handled = handleAutocompleteKeyDown(e, queryText, (selected) => {
      setQueryText(selected);
      resetNavigation();
    });

    if (handled) return;

    // Handle Tab for old ghost text (if still present)
    if (e.key === "Tab" && ghostText) {
      e.preventDefault();
      const newQuery = queryText + ghostText;
      setQueryText(newQuery);
      setGhostText("");

      setTimeout(() => {
        const textarea = textareaRef.current;
        textarea.setSelectionRange(newQuery.length, newQuery.length);
      }, 0);
    }
    // Handle Escape
    else if (e.key === "Escape") {
      setGhostText("");
      hideAutocompleteSuggestions();
    }
    // Handle Arrow Up - Previous query
    else if (
      e.key === "ArrowUp" &&
      sessionQueries.length > 0 &&
      !showAutocompleteSuggestions
    ) {
      e.preventDefault();
      const previousQuery = navigateHistory("up", queryText);
      if (previousQuery !== null) {
        setQueryText(previousQuery);
        setTimeout(() => {
          const textarea = textareaRef.current;
          if (textarea) {
            textarea.setSelectionRange(
              previousQuery.length,
              previousQuery.length
            );
          }
        }, 0);
      }
    }
    // Handle Arrow Down - Next query
    else if (
      e.key === "ArrowDown" &&
      sessionQueries.length > 0 &&
      !showAutocompleteSuggestions
    ) {
      e.preventDefault();
      const nextQuery = navigateHistory("down", queryText);
      if (nextQuery !== null) {
        setQueryText(nextQuery);
        setTimeout(() => {
          const textarea = textareaRef.current;
          if (textarea) {
            textarea.setSelectionRange(nextQuery.length, nextQuery.length);
          }
        }, 0);
      }
    }
  };

  useEffect(() => {
    fetchQueryState();
  }, []);

  const fetchQueryState = async () => {
    try {
      const response = await axios.get("/api/query");

      if (response.data.success) {
        setDbType(response.data.db_type);
        setHandlerName(response.data.handler);
        setCurrentDb(response.data.current_db);
      }
    } catch (err) {
      console.error("Failed to fetch query state:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteQuery = async (e) => {
    e.preventDefault();
    setError("");
    setResult(null);

    if (!queryText.trim()) {
      setError("Query cannot be empty");
      return;
    }

    try {
      const response = await axios.post("/api/query", { query: queryText });

      if (response.data.success) {
        // Save to history
        await addQuery(queryText);

        setResult(response.data.result);
        setCurrentDb(response.data.current_db);
      } else {
        setError(response.data.error || "Query execution failed");
      }
    } catch (err) {
      setError(
        "Failed to execute query: " + (err.response?.data?.error || err.message)
      );
    }
  };

  const getPlaceholder = () => {
    if (dbType === "sql") {
      return `Enter SQL queries (separate multiple statements with semicolons)...

Examples:
  SELECT * FROM users;
  INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com');
  
Database commands:
  CREATE DATABASE mydb;
  USE mydb;
  DROP DATABASE olddb;`;
    } else {
      return `Enter NoSQL query or command...

Database Commands:
  USE NosqlTrial2;
  CREATE DATABASE mydb;
  DROP DATABASE olddb;
  SHOW DATABASES;
  SHOW COLLECTIONS;
  CREATE COLLECTION mycollection;
  DROP COLLECTION mycollection;

Query Examples (JSON format):
  {"table": "Trial1", "condition": {}}
  {"table": "Trial1", "condition": {"age": {"$gt": 30}}}`;
    }
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
          <div className="loading">Loading query console...</div>
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
            maxWidth: "95%",
            margin: "20px auto",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "15px",
            }}
          >
            <h2 style={{ color: "#f0f0f0" }}>
              Query Console
              {currentDb && (
                <span style={{ color: "#666", fontSize: "0.8em" }}>
                  — {currentDb} ({dbType.toUpperCase()})
                </span>
              )}
            </h2>
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                navigate("/");
              }}
              style={{ color: "#e6d8f7ff" }}
            >
              ← Home
            </a>
          </div>

          {error && (
            <div
              style={{
                background: "#ffebee",
                borderLeft: "4px solid #f44336",
                padding: "12px",
                margin: "10px 0",
                borderRadius: "4px",
                color: "#c62828",
              }}
            >
              <strong>ERROR:</strong> {error}
            </div>
          )}

          {!error && result && (
            <div
              style={{
                background: "#e8f5e9",
                borderLeft: "4px solid #4caf50",
                padding: "12px",
                margin: "10px 0",
                borderRadius: "4px",
                color: "#2e7d32",
              }}
            >
              <strong>SUCCESS:</strong> Query executed successfully
            </div>
          )}

          <form onSubmit={handleExecuteQuery}>
            <div style={{ position: "relative" }}>
              {/* Ghost text overlay - keep if you want the old autocomplete too */}
              <div
                style={{
                  position: "absolute",
                  top: "18px",
                  left: "18px",
                  right: "12px",
                  bottom: "12px",
                  pointerEvents: "none",
                  fontFamily: "'Consolas', 'Monaco', monospace",
                  fontSize: "14px",
                  padding: "0",
                  color: "transparent",
                  whiteSpace: "pre-wrap",
                  wordWrap: "break-word",
                  overflow: "hidden",
                  lineHeight: "1.5",
                }}
              >
                {queryText}
                <span
                  style={{
                    color: "#ffffffff",
                    opacity: 0.8,
                    fontWeight: "bold",
                  }}
                >
                  {ghostText}
                </span>
              </div>

              <textarea
                ref={textareaRef}
                value={queryText}
                onChange={handleQueryChange}
                onKeyDown={handleKeyDown}
                onBlur={() => {
                  setTimeout(() => hideAutocompleteSuggestions(), 200);
                }}
                rows={dbType === "sql" ? 12 : 16}
                placeholder={getPlaceholder()}
                style={{
                  width: "100%",
                  fontFamily: "'Consolas', 'Monaco', monospace",
                  fontSize: "14px",
                  padding: "12px",
                  border: "1px solid #ccc",
                  borderRadius: "4px",
                  background: "transparent",
                  color: "#f0f0f0",
                  position: "relative",
                  zIndex: 1,
                  lineHeight: "1.5",
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

            {ghostText && (
              <div
                style={{
                  fontSize: "12px",
                  color: "#999",
                  marginTop: "4px",
                }}
              >
                💡 Press{" "}
                <kbd
                  style={{
                    padding: "2px 6px",
                    background: "#333",
                    borderRadius: "3px",
                  }}
                >
                  Tab
                </kbd>{" "}
                to accept suggestion
              </div>
            )}

            <div
              style={{
                fontSize: "12px",
                color: "#999",
                marginTop: "4px",
              }}
            >
              💡 Press{" "}
              <kbd
                style={{
                  padding: "2px 6px",
                  background: "#333",
                  borderRadius: "3px",
                }}
              >
                ↑
              </kbd>{" "}
              to view previous query,{" "}
              <kbd
                style={{
                  padding: "2px 6px",
                  background: "#333",
                  borderRadius: "3px",
                }}
              >
                ↓
              </kbd>{" "}
              to view next query
              {sessionQueries.length > 0 &&
                ` (${sessionQueries.length} in history)`}
              {showAutocompleteSuggestions &&
                autocompleteSuggestions.length > 0 &&
                " | Use arrow keys + Enter to select suggestion"}
            </div>

            <br />
            <button
              type="submit"
              style={{
                background: "#9370db",
                color: "white",
                border: "none",
                padding: "10px 30px",
                fontSize: "16px",
                borderRadius: "5px",
                cursor: "pointer",
                transition: "background 0.3s",
              }}
              onMouseOver={(e) => (e.target.style.background = "#4b0082")}
              onMouseOut={(e) => (e.target.style.background = "#9370db")}
            >
              ▶ Execute
            </button>
          </form>

          {result && (
            <div style={{ marginTop: "20px" }}>
              <h3 style={{ textAlign: "center", color: "#f0f0f0" }}>
                Results:
              </h3>

              {Array.isArray(result) &&
                result.map((res, idx) => (
                  <div key={idx}>
                    <div
                      style={{
                        background: "#e3f2fd",
                        padding: "8px 12px",
                        margin: "15px auto 5px auto",
                        borderLeft: "4px solid #2196f3",
                        fontWeight: "bold",
                        width: "90%",
                        color: "black",
                      }}
                    >
                      Statement {idx + 1}
                    </div>

                    {/* ✅ FIX: Check for procedure results first */}
                    {typeof res === "object" &&
                    res !== null &&
                    !Array.isArray(res) &&
                    res.result_type === "table" ? (
                      /* Procedure table result */
                      Array.isArray(res.result) && res.result.length > 0 ? (
                        <>
                          <div
                            style={{
                              maxWidth: "93%",
                              margin: "20px auto",
                              overflowX: "auto",
                              padding: "12px",
                            }}
                          >
                            <table
                              className="result-table"
                              style={{
                                minWidth: "600px",
                                borderCollapse: "separate",
                                border: "2px solid black",
                                width: "100%",
                              }}
                              cellPadding="8"
                            >
                              <thead>
                                <tr>
                                  {Object.keys(res.result[0]).map((key, i) => (
                                    <th
                                      style={{
                                        border: "1px solid black",
                                        padding: "12px",
                                        background: "#f0f0f0",
                                        color: "black",
                                      }}
                                      key={i}
                                    >
                                      {key}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {res.result.map((row, rowIdx) => (
                                  <tr key={rowIdx}>
                                    {Object.values(row).map((value, valIdx) => (
                                      <td
                                        style={{
                                          border: "1px solid black",
                                          padding: "12px",
                                          color: "black",
                                          background: "white",
                                        }}
                                        key={valIdx}
                                      >
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
                              background: "#e8f5e9",
                              borderLeft: "4px solid #4caf50",
                              padding: "12px",
                              margin: "10px auto",
                              borderRadius: "4px",
                              width: "90%",
                              color: "black",
                            }}
                          >
                            {res.result.length} row
                            {res.result.length !== 1 ? "s" : ""} returned
                          </div>
                        </>
                      ) : (
                        <div
                          style={{
                            background: "#e8f5e9",
                            borderLeft: "4px solid #4caf50",
                            padding: "12px",
                            margin: "10px auto",
                            borderRadius: "4px",
                            width: "90%",
                            color: "black",
                          }}
                        >
                          Procedure executed successfully. No rows returned.
                        </div>
                      )
                    ) : typeof res === "object" &&
                      res !== null &&
                      !Array.isArray(res) &&
                      res.result_type === "status" ? (
                      /* Procedure status result */
                      <div
                        style={{
                          background: "#e8f5e9",
                          borderLeft: "4px solid #4caf50",
                          padding: "12px",
                          margin: "10px auto",
                          borderRadius: "4px",
                          width: "90%",
                          color: "black",
                        }}
                      >
                        {res.result?.status ||
                          `Rows affected: ${res.rows_affected || 0}`}
                      </div>
                    ) : typeof res === "object" &&
                      res !== null &&
                      !Array.isArray(res) &&
                      (res.status || res.rows_affected !== undefined) ? (
                      /* Regular status/rows_affected result */
                      <div
                        style={{
                          background: "#e8f5e9",
                          borderLeft: "4px solid #4caf50",
                          padding: "12px",
                          margin: "10px auto",
                          borderRadius: "4px",
                          width: "90%",
                          color: "black",
                        }}
                      >
                        {res.status && <div>{res.status}</div>}
                        {res.rows_affected !== undefined && (
                          <div>Rows affected: {res.rows_affected}</div>
                        )}
                      </div>
                    ) : Array.isArray(res) ? (
                      /* Array of results (SQL or NoSQL documents) */
                      res.length > 0 ? (
                        <>
                          {dbType === "nosql" ? (
                            /* NoSQL: Field-Value format (horizontal layout) */
                            <>
                              {res.map((doc, docIdx) => (
                                <div
                                  key={docIdx}
                                  style={{
                                    maxWidth: "93%",
                                    margin: "20px auto",
                                    overflowX: "auto",
                                    padding: "12px",
                                  }}
                                >
                                  <div
                                    style={{
                                      background: "#f0f0f0",
                                      padding: "8px 12px",
                                      marginBottom: "10px",
                                      borderRadius: "4px",
                                      fontWeight: "bold",
                                      color: "black",
                                    }}
                                  >
                                    Document {docIdx + 1}
                                  </div>
                                  <table
                                    className="result-table"
                                    style={{
                                      minWidth: "600px",
                                      borderCollapse: "separate",
                                      border: "2px solid black",
                                      width: "100%",
                                    }}
                                    cellPadding="8"
                                  >
                                    <tbody>
                                      <tr>
                                        <th
                                          style={{
                                            border: "1px solid black",
                                            padding: "12px",
                                            background: "#f0f0f0",
                                            color: "black",
                                            width: "30%",
                                          }}
                                        >
                                          Field
                                        </th>
                                        <th
                                          style={{
                                            border: "1px solid black",
                                            padding: "12px",
                                            background: "#f0f0f0",
                                            color: "black",
                                          }}
                                        >
                                          Value
                                        </th>
                                      </tr>
                                      {Object.entries(doc).map(
                                        ([key, value], i) => (
                                          <tr key={i}>
                                            <td
                                              style={{
                                                border: "1px solid black",
                                                padding: "12px",
                                                background: "white",
                                                color: "black",
                                                fontWeight: "bold",
                                              }}
                                            >
                                              {key}
                                            </td>
                                            <td
                                              style={{
                                                border: "1px solid black",
                                                padding: "12px",
                                                background: "white",
                                                color: "black",
                                              }}
                                            >
                                              {value !== null &&
                                              value !== undefined
                                                ? typeof value === "object"
                                                  ? JSON.stringify(value)
                                                  : String(value)
                                                : "NULL"}
                                            </td>
                                          </tr>
                                        )
                                      )}
                                    </tbody>
                                  </table>
                                </div>
                              ))}
                              <div
                                style={{
                                  background: "#e8f5e9",
                                  borderLeft: "4px solid #4caf50",
                                  padding: "12px",
                                  margin: "10px auto",
                                  borderRadius: "4px",
                                  width: "90%",
                                  color: "black",
                                }}
                              >
                                {res.length} document
                                {res.length !== 1 ? "s" : ""} returned
                              </div>
                            </>
                          ) : (
                            /* SQL: Traditional table format (vertical layout) */
                            <>
                              <div
                                style={{
                                  maxWidth: "93%",
                                  margin: "20px auto",
                                  overflowX: "auto",
                                  padding: "12px",
                                }}
                              >
                                <table
                                  className="result-table"
                                  style={{
                                    minWidth: "600px",
                                    borderCollapse: "separate",
                                    border: "2px solid black",
                                    width: "100%",
                                  }}
                                  cellPadding="8"
                                >
                                  <thead>
                                    <tr>
                                      {Object.keys(res[0]).map((key, i) => (
                                        <th
                                          style={{
                                            border: "1px solid black",
                                            padding: "12px",
                                            background: "#f0f0f0",
                                            color: "black",
                                          }}
                                          key={i}
                                        >
                                          {key}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {res.map((row, rowIdx) => (
                                      <tr key={rowIdx}>
                                        {Object.values(row).map(
                                          (value, valIdx) => (
                                            <td
                                              style={{
                                                border: "1px solid black",
                                                padding: "12px",
                                                color: "black",
                                                background: "white",
                                              }}
                                              key={valIdx}
                                            >
                                              {value !== null &&
                                              value !== undefined
                                                ? typeof value === "object"
                                                  ? JSON.stringify(value)
                                                  : String(value)
                                                : "NULL"}
                                            </td>
                                          )
                                        )}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                              <div
                                style={{
                                  background: "#e8f5e9",
                                  borderLeft: "4px solid #4caf50",
                                  padding: "12px",
                                  margin: "10px auto",
                                  borderRadius: "4px",
                                  width: "90%",
                                  color: "black",
                                }}
                              >
                                {res.length} row{res.length !== 1 ? "s" : ""}{" "}
                                returned
                              </div>
                            </>
                          )}
                        </>
                      ) : (
                        <div
                          style={{
                            background: "#e8f5e9",
                            borderLeft: "4px solid #4caf50",
                            padding: "12px",
                            margin: "10px auto",
                            borderRadius: "4px",
                            width: "90%",
                            color: "black",
                          }}
                        >
                          Query executed successfully. No rows returned.
                        </div>
                      )
                    ) : typeof res === "object" && res !== null ? (
                      /* Single object result (field-value pairs) */
                      <div
                        style={{
                          maxWidth: "93%",
                          margin: "20px auto",
                          overflowX: "auto",
                          padding: "12px",
                        }}
                      >
                        <table
                          className="result-table"
                          style={{
                            minWidth: "600px",
                            borderCollapse: "separate",
                            border: "2px solid black",
                            width: "100%",
                          }}
                          cellPadding="8"
                        >
                          <tbody>
                            <tr>
                              <th
                                style={{
                                  border: "1px solid black",
                                  padding: "12px",
                                  background: "#f0f0f0",
                                  color: "black",
                                }}
                              >
                                Field
                              </th>
                              <th
                                style={{
                                  border: "1px solid black",
                                  padding: "12px",
                                  background: "#f0f0f0",
                                  color: "black",
                                }}
                              >
                                Value
                              </th>
                            </tr>
                            {Object.entries(res).map(([key, value], i) => (
                              <tr key={i}>
                                <td
                                  style={{
                                    border: "1px solid black",
                                    padding: "12px",
                                    background: "white",
                                    color: "black",
                                  }}
                                >
                                  <strong>{key}</strong>
                                </td>
                                <td
                                  style={{
                                    border: "1px solid black",
                                    padding: "12px",
                                    background: "white",
                                    color: "black",
                                  }}
                                >
                                  {value !== null && value !== undefined
                                    ? typeof value === "object"
                                      ? JSON.stringify(value)
                                      : String(value)
                                    : "NULL"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
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
                        {JSON.stringify(res, null, 2)}
                      </pre>
                    )}
                  </div>
                ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default GlobalQuery;
