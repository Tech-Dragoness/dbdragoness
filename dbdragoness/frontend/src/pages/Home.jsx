import React, { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import Sidebar from "../components/Sidebar";
import RenameDatabaseModal from "../components/RenameDatabaseModal";
import ConvertDatabaseModal from "../components/ConvertDatabaseModal";
import ConnectionStringCard from "../components/ConnectionStringCard";

function Home() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [databases, setDatabases] = useState([]);
  const [dbType, setDbType] = useState("sql");
  const [currentHandler, setCurrentHandler] = useState("");
  const [availableHandlers, setAvailableHandlers] = useState([]);
  const [newDbName, setNewDbName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [allDatabases, setAllDatabases] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchTimeout, setSearchTimeout] = useState(null);
  const [page, setPage] = useState(1);
  const [perPage] = useState(10);
  const [totalPages, setTotalPages] = useState(1);
  const [totalDatabases, setTotalDatabases] = useState(0);
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renameDbName, setRenameDbName] = useState("");
  const [convertModalOpen, setConvertModalOpen] = useState(false);
  const [convertDbName, setConvertDbName] = useState("");

  useEffect(() => {
    fetchDatabases();
  }, []);

  useEffect(() => {
    checkCredentialsAndLoadData();
  }, []);

  useEffect(() => {
    if (searchTerm) {
      performSearch(searchTerm);
    }
  }, [page]);

  const fetchDatabases = async () => {
    try {
      setLoading(true);
      const response = await axios.get("/api/databases");

      if (response.data.success) {
        const dbs = response.data.databases;
        setAllDatabases(dbs);
        setDatabases(dbs);
        setDbType(response.data.db_type);
        setCurrentHandler(response.data.handler);
        setAvailableHandlers(response.data.available_handlers || []);

        // Calculate pagination
        const total = response.data.databases.length;
        setTotalDatabases(total);
        setTotalPages(Math.ceil(total / perPage));
      } else {
        setError(response.data.error || "Failed to fetch databases");
      }
    } catch (err) {
      console.error("Failed to fetch databases:", err);
    } finally {
      setLoading(false);
    }
  };

  const checkCredentialsAndLoadData = async () => {
    try {
      // ✅ First check if credentials are needed
      const credCheck = await axios.get("/api/check_credentials");

      if (credCheck.data.success && credCheck.data.needs_credentials) {
        // Redirect to credentials page
        navigate(`/credentials/${credCheck.data.handler}`);
        return; // Don't load data
      }

      // ✅ Credentials OK, proceed to load data
      fetchDatabases();
    } catch (err) {
      console.error("Failed to check credentials:", err);
      // Proceed anyway
      fetchDatabases();
    }
  };

  const handleRenameSuccess = (newName) => {
    fetchDatabases();
    // Optionally navigate to the renamed database
    // navigate(`/db/${newName}`);
  };

  const performSearch = async (term) => {
    setSearching(true);
    try {
      const response = await axios.get("/api/databases/search", {
        params: { q: term, page, per_page: perPage },
      });

      if (response.data.success) {
        setDatabases(response.data.databases);
        setTotalPages(response.data.total_pages);
        setTotalDatabases(response.data.total); // ADD THIS LINE
      }
    } catch (err) {
      console.error("Search error:", err);
    } finally {
      setSearching(false);
    }
  };

  const handleSearchChange = (value) => {
    setSearchTerm(value);
    setPage(1); // Reset to page 1 when search term changes

    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }

    const timeout = setTimeout(() => {
      performSearch(value);
    }, 300);

    setSearchTimeout(timeout);
  };

  const handleCreateDatabase = async (e) => {
    e.preventDefault();
    setError("");

    if (!newDbName) {
      setError(
        "Database name cannot be empty!",
      );
      return;
    }

    else if (!newDbName.match(/^[a-zA-Z][a-zA-Z0-9_]*$/)) {
      setError(
        "Database name must start with a letter, contain only letters, numbers, underscores.",
      );
      return;
    }

    if (databases.includes(newDbName)) {
      setError("Database name already exists.");
      return;
    }

    try {
      const response = await axios.post("/api/databases", {
        action: "create",
        db_name: newDbName,
      });

      if (response.data.success) {
        setNewDbName("");
        fetchDatabases();
        navigate(`/db/${newDbName}`);
      } else {
        setError(response.data.error || "Failed to create database");
      }
    } catch (err) {
      console.error("Create database error:", err);
      // Extract the actual error message from the response
      const errorMessage = err.response?.data?.error || "Failed to create database";
      setError(errorMessage);
    }
  };

  const handleDeleteDatabase = async (dbName) => {
    if (
      !window.confirm(`Are you sure you want to delete database ${dbName}?`)
    ) {
      return;
    }

    try {
      const response = await axios.post("/api/databases", {
        action: "delete",
        db_name: dbName,
      });

      if (response.data.success) {
        setAllDatabases(prev => prev.filter(db => db !== dbName));
        setDatabases(prev => prev.filter(db => db !== dbName));
        if (searchTerm) {
          performSearch(searchTerm);
        } else {
          fetchDatabases();
        }
      } else {
        setError(response.data.error || "Failed to delete database");
      }
    } catch (err) {
      console.error("Delete database error:", err);
      // Extract the actual error message from the response
      const errorMessage = err.response?.data?.error || "Failed to delete database";
      setError(errorMessage);
    }
  };

  const switchHandler = async (handlerName) => {
    setError("");
    setLoading(true);

    try {
      const response = await axios.post("/api/switch_handler", {
        type: dbType,
        handler: handlerName,
      });

      if (response.data.success) {
        setCurrentHandler(response.data.handler);
        setDbType(response.data.db_type);
        setAvailableHandlers(response.data.available_handlers || []);

        // CRITICAL: Check if the new handler needs credentials
        const credCheck = await axios.get("/api/check_credentials");
        if (credCheck.data.success && credCheck.data.needs_credentials) {
          navigate(`/credentials/${credCheck.data.handler}`, { replace: true });
          return; // Don't reload data — user must login first
        }

        // Only fetch databases if credentials are OK
        fetchDatabases();
      } else {
        setError(response.data.error || "Failed to switch handler");
      }
    } catch (err) {
      console.error("Switch handler error:", err);
      setError("Failed to switch handler");
    } finally {
      setLoading(false);
    }
  };

  // Only slice if we're NOT searching (search results are already paginated by backend)
  const paginatedDatabases = searchTerm 
    ? databases 
    : databases.slice((page - 1) * perPage, page * perPage);

  const clearSearch = () => {
    setSearchTerm("");
    setDatabases(allDatabases);
    setTotalPages(Math.ceil(allDatabases.length / perPage));
    setPage(1);
  };

  if (loading) {
    return (
      <>
        <Sidebar dbType={dbType} handlerName={currentHandler} />
        <div className="center">
          <div className="loading">Loading databases...</div>
        </div>
      </>
    );
  }

  return (
    <>
      <Sidebar dbType={dbType} handlerName={currentHandler} />
      <div className="center">
        <h1>
          Database Manager ({dbType.toUpperCase()} - {currentHandler})
        </h1>

        {/* Handler Selection */}
        <div style={{ marginBottom: "20px" }}>
          <label htmlFor="handler_select">Database Type:</label>
          <select
            id="handler_select"
            value={currentHandler}
            onChange={(e) => switchHandler(e.target.value)}
          >
            {availableHandlers.map((handler) => (
              <option key={handler} value={handler}>
                {handler}
              </option>
            ))}
          </select>
        </div>

        {error && <p style={{ color: "red" }}>{error}</p>}

        {/* Search Bar */}
        <div style={{ margin: "20px 0", textAlign: "left" }}>
          <input
            type="text"
            id="search-databases"
            placeholder="Search databases on this page..."
            value={searchTerm}
            onChange={(e) => handleSearchChange(e.target.value)}
            style={{
              padding: "8px 20px",
              width: "550px",
              maxWidth: "90%",
              border: "1.5px solid #9370db",
              borderRadius: "10px",
              fontSize: "16px",
              outline: "none",
              background: "rgba(147, 112, 219, 0.1)",
              boxShadow: "0 4px 15px rgba(147, 112, 219, 0.3)",
              transition: "all 0.3s",
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
            id="search-info"
            style={{ marginTop: "8px", fontSize: "14px", color: "#666" }}
          >
            {searchTerm &&
              (searching ? (
                <span style={{ color: "#6a5acd" }}>🔍 Searching...</span>
              ) : paginatedDatabases.length === 0 ? (
                <span style={{ color: "#dc3545" }}>⚠️ No results found.</span>
              ) : (
                <span style={{ color: "#28a745" }}>
                  ✓ {totalDatabases} database{totalDatabases !== 1 ? "s" : ""}{" "}
                  match
                </span>
              ))}
          </div>
        </div>

        {/* Create Database Form - All on ONE line */}
        <form
          onSubmit={handleCreateDatabase}
          id="db_form"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
            whiteSpace: "nowrap",
            width: "100%",
            maxWidth: "400px",
            minWidth: "280px",
          }}
        >
          <div
            style={{
              position: "relative",
              flexGrow: 1,
              minWidth: 0,
              display: "flex",
              alignItems: "center",
            }}
          >
            <input
              type="text"
              id="db_name_input"
              name="db_name"
              placeholder="New Database Name"
              value={newDbName}
              onChange={(e) => {
                const newValue = e.target.value;
                if (newValue.length <= 63) {
                  setNewDbName(newValue);
                }
              }}
              maxLength={63}
              style={{
                width: "100%",
                padding: "8px 12px",
                paddingRight: "60px", // Make room for counter
                borderRadius: "4px",
                outline: "none",
                boxShadow: "0 0 0 2px rgba(147,112,219,0.2)",
                fontSize: "14px",
              }}
            />
            {/* Tiny live counter - positioned inside/next to input */}
            <span
              style={{
                position: "absolute",
                right: "12px",
                fontSize: "12px",
                color: "#6b7280",
                pointerEvents: "none",
                padding: "0 4px",
              }}
            >
              {newDbName.length}/63
            </span>
          </div>

          {/* Create button - stays on the same line */}
          <button
            type="submit"
            style={{
              backgroundColor: "#9370db",
              color: "white",
              padding: "8px 24px",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
              whiteSpace: "nowrap",
              flexShrink: 0,
              fontSize: "14px",
              fontWeight: "500",
            }}
            onMouseOver={(e) =>
              (e.currentTarget.style.backgroundColor = "#7c5bbb")
            }
            onMouseOut={(e) =>
              (e.currentTarget.style.backgroundColor = "#9370db")
            }
          >
            Create
          </button>
        </form>

        {/* Databases Table */}
        <table className="db-table">
          <thead>
            <tr>
              <th>Database Name</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {paginatedDatabases.map((db) => (
              <tr key={db}>
                <td>{db}</td>
                <td>
                  <button
                    className="view-btn"
                    onClick={() => navigate(`/db/${db}`)}
                    style={{ background: "#1e9530" }}
                  >
                    View
                  </button>
                  <button
                    onClick={() => {
                      setRenameDbName(db);
                      setRenameModalOpen(true);
                    }}
                    style={{ background: "#ff9800" }}
                  >
                    Rename
                  </button>
                  <button
                    onClick={() => {
                      setConvertDbName(db);
                      setConvertModalOpen(true);
                    }}
                    style={{ background: "#334155" }}
                  >
                    Convert
                  </button>
                  <button
                    onClick={() => {
                      // Find which page this database is on
                      const dbIndex = databases.indexOf(db);
                      const targetPage = Math.floor(dbIndex / perPage) + 1;

                      // Navigate to correct page first
                      if (targetPage !== page) {
                        setPage(targetPage);
                      }

                      // Wait for page change, then scroll
                      setTimeout(
                        () => {
                          const connSection = document.getElementById(
                            `conn-${db}`,
                          );
                          if (connSection) {
                            connSection.scrollIntoView({
                              behavior: "smooth",
                              block: "center",
                            });
                            // Open the details element
                            setTimeout(() => {
                              const detailsEl =
                                connSection.querySelector("details");
                              if (detailsEl) {
                                detailsEl.open = true;
                              }
                            }, 500);
                          } else {
                            // If not found, check again after another delay (page might still be rendering)
                            setTimeout(() => {
                              const retrySection = document.getElementById(
                                `conn-${db}`,
                              );
                              if (retrySection) {
                                retrySection.scrollIntoView({
                                  behavior: "smooth",
                                  block: "center",
                                });
                                setTimeout(() => {
                                  const detailsEl =
                                    retrySection.querySelector("details");
                                  if (detailsEl) {
                                    detailsEl.open = true;
                                  }
                                }, 300);
                              }
                            }, 200);
                          }
                        },
                        targetPage !== page ? 300 : 0,
                      );
                    }}
                    style={{ background: "#17a2b8" }}
                  >
                    Connection Info
                  </button>
                  <button
                    onClick={() => handleDeleteDatabase(db)}
                    style={{ background: "#dc3545" }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

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
              Page {page} of {totalPages} ({totalDatabases} total)
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

        {/* Connection Strings Section - PAGINATED */}
        {databases.length > 0 && (
          <div style={{ marginTop: "40px" }}>
            <h2>Connection Strings</h2>
            <p style={{ color: "white", fontSize: "0.9em" }}>
              ⚠️ Note: Replace placeholder values with your actual credentials
              where needed.
            </p>
            <div
              style={{
                background: "#1e0033e6",
                padding: "15px",
                borderRadius: "5px",
                marginTop: "20px",
              }}
            >
              {/* Only render paginated databases */}
              {paginatedDatabases.map((db) => (
                <ConnectionStringCard
                  key={db}
                  dbName={db}
                  handlerName={currentHandler}
                />
              ))}
            </div>

            {/* Pagination for Connection Strings (matches database pagination) */}
            {totalPages > 1 && (
              <div className="pagination" style={{ marginTop: "20px" }}>
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
                  Page {page} of {totalPages}
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

        {renameModalOpen && (
          <RenameDatabaseModal
            dbName={renameDbName}
            onClose={() => setRenameModalOpen(false)}
            onSuccess={handleRenameSuccess}
          />
        )}

        {convertModalOpen && (
          <ConvertDatabaseModal
            dbName={convertDbName}
            currentDbType={dbType}
            currentHandler={currentHandler}
            onClose={() => setConvertModalOpen(false)}
            onSuccess={(newDbName, newType, newHandler) => {
              // Switch to the new database
              window.location.href = `/react/db/${newDbName}`;
            }}
          />
        )}
      </div>
    </>
  );
}

export default Home;
