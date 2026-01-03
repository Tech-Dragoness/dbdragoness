import React, { useState, useEffect } from "react";
import axios from "axios";

function ConvertDatabaseModal({
  dbName,
  currentDbType,
  currentHandler,
  onClose,
  onSuccess,
}) {
  const [targetType, setTargetType] = useState("");
  const [targetHandler, setTargetHandler] = useState("");
  const [targetDbName, setTargetDbName] = useState(dbName + "_converted");
  const [availableHandlers, setAvailableHandlers] = useState({
    sql: [],
    nosql: [],
  });
  const [searchTerm, setSearchTerm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [currentItem, setCurrentItem] = useState("");
  const [converting, setConverting] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    fetchAvailableHandlers();
  }, []);

  const fetchAvailableHandlers = async () => {
    try {
      const response = await axios.get("/api/available_handlers");
      if (response.data.success) {
        setAvailableHandlers({
          sql: response.data.sql,
          nosql: response.data.nosql,
        });
      }
    } catch (err) {
      console.error("Failed to fetch handlers:", err);
    }
  };

  const getFilteredHandlers = () => {
    if (!targetType) return [];

    const handlers =
      targetType === "sql" ? availableHandlers.sql : availableHandlers.nosql;

    // Filter out current handler
    const filtered = handlers.filter(
      (h) => !(h === currentHandler && targetType === currentDbType)
    );

    if (!searchTerm) return filtered;

    const lower = searchTerm.toLowerCase();

    // Prioritize handlers that START with the search term
    const startsWith = filtered.filter((h) =>
      h.toLowerCase().startsWith(lower)
    );
    const contains = filtered.filter(
      (h) =>
        h.toLowerCase().includes(lower) && !h.toLowerCase().startsWith(lower)
    );

    return [...startsWith, ...contains];
  };

  const handleConvert = async (e) => {
    e.preventDefault();
    setError("");

    if (!targetType || !targetHandler) {
      setError("Please select target database type and handler");
      return;
    }

    if (!targetDbName.match(/^[a-zA-Z][a-zA-Z0-9_]*$/)) {
      setError(
        "Database name must start with a letter, contain only letters, numbers, underscores."
      );
      return;
    }

    setLoading(true);
    setConverting(true);
    setProgress(0);

    try {
      const response = await fetch("/api/databases/convert", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          source_db: dbName,
          target_db_name: targetDbName,
          target_type: targetType,
          target_handler: targetHandler,
        }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.substring(6));

              if (data.error) {
                setError(data.error);
                setConverting(false);
                setLoading(false);
                return;
              }

              if (data.progress !== undefined) {
                setProgress(data.progress);
                setStage(data.stage || "");
                setCurrentItem(data.current || "");
              }

              if (data.progress === 100) {
                setSuccessMessage(
                  `Successfully converted ${dbName} to ${targetDbName}!`
                );
                setTimeout(() => {
                  onSuccess(targetDbName, targetType, targetHandler);
                  onClose();
                }, 3000);
              }
            } catch (parseErr) {
              console.error("Failed to parse SSE data:", parseErr);
            }
          }
        }
      }
    } catch (err) {
      console.error("Conversion error:", err);
      setError(err.message || "Failed to convert database");
      setConverting(false);
      setLoading(false);
    }
  };
  const filteredHandlers = getFilteredHandlers();
  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        background: "rgba(0, 0, 0, 0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
      }}
      onClick={!converting ? onClose : undefined}
    >
      <div
        style={{
          background: "linear-gradient(135deg, #1e0033, #3a0066)",
          padding: "30px",
          borderRadius: "15px",
          maxWidth: "600px",
          width: "95%",
          border: "2px solid #9370db",
          boxShadow: "0 10px 40px rgba(147, 112, 219, 0.6)",
          maxHeight: "90vh",
          overflowY: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ color: "#f0f0f0", marginBottom: "10px" }}>
          Convert Database
        </h2>
        <p style={{ color: "#ccc", fontSize: "0.9em", marginBottom: "20px" }}>
          Current: <strong>{dbName}</strong> ({currentDbType.toUpperCase()} -{" "}
          {currentHandler})
        </p>
        {!converting && !successMessage && (
          <div
            style={{
              background: "rgba(255, 193, 7, 0.1)",
              border: "1px solid #ffc107",
              borderRadius: "5px",
              padding: "15px",
              marginBottom: "20px",
              color: "#ffc107",
              fontSize: "0.9em",
            }}
          >
            <strong>⚠️ Important:</strong>
            <ul style={{ marginTop: "10px", paddingLeft: "20px" }}>
              <li>The original database will remain untouched</li>
              <li>
                We strive to transfer all metadata (triggers, procedures,
                constraints)
              </li>
              <li>
                Some metadata may be lost if the target database doesn't support
                it
              </li>
              <li>
                Please verify the target database capabilities before converting
              </li>
            </ul>
          </div>
        )}

        {error && (
          <div
            className="error"
            style={{
              marginBottom: "15px",
              padding: "10px",
              background: "rgba(220, 53, 69, 0.2)",
              border: "1px solid #dc3545",
              borderRadius: "5px",
              color: "#ff6b6b",
            }}
          >
            {error}
          </div>
        )}

        {successMessage && (
          <div
            style={{
              padding: "20px",
              background: "rgba(40, 167, 69, 0.2)",
              border: "1px solid #28a745",
              borderRadius: "5px",
              color: "#28a745",
              textAlign: "center",
              fontSize: "1.1em",
            }}
          >
            ✅ {successMessage}
            <p style={{ marginTop: "10px", fontSize: "0.9em" }}>
              Redirecting in 3 seconds...
            </p>
          </div>
        )}

        {converting && !successMessage && (
          <div style={{ marginBottom: "20px" }}>
            <div
              style={{
                background: "rgba(147, 112, 219, 0.2)",
                borderRadius: "10px",
                overflow: "hidden",
                marginBottom: "10px",
              }}
            >
              <div
                style={{
                  height: "30px",
                  background: "linear-gradient(90deg, #9370db, #ba55d3)",
                  width: `${progress}%`,
                  transition: "width 0.3s ease",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "white",
                  fontWeight: "bold",
                  fontSize: "0.9em",
                }}
              >
                {progress}%
              </div>
            </div>
            <p
              style={{ color: "#ccc", fontSize: "0.9em", textAlign: "center" }}
            >
              {stage === "export" && "Exporting data..."}
              {stage === "switch" && "Switching handler..."}
              {stage === "import" && "Importing data..."}
              {stage === "complete" && "Finalizing..."}
              {currentItem && (
                <span
                  style={{
                    display: "block",
                    marginTop: "5px",
                    color: "#9370db",
                  }}
                >
                  {currentItem}
                </span>
              )}
            </p>
          </div>
        )}

        {!converting && !successMessage && (
          <form onSubmit={handleConvert}>
            <div style={{ marginBottom: "20px" }}>
              <label
                style={{
                  color: "#f0f0f0",
                  display: "block",
                  marginBottom: "5px",
                }}
              >
                Target Database Type:
              </label>
              <select
                value={targetType}
                onChange={(e) => {
                  setTargetType(e.target.value);
                  setTargetHandler("");
                  setSearchTerm("");
                }}
                style={{
                  width: "100%",
                  padding: "10px",
                  border: "1.5px solid #9370db",
                  borderRadius: "5px",
                  background: "rgba(147, 112, 219, 0.1)",
                  color: "#f0f0f0",
                  fontSize: "14px",
                }}
                required
              >
                <option value="">-- Select Type --</option>
                <option value="sql">SQL</option>
                <option value="nosql">NoSQL</option>
              </select>
            </div>

            {targetType && (
              <div style={{ marginBottom: "20px" }}>
                <label
                  style={{
                    color: "#f0f0f0",
                    display: "block",
                    marginBottom: "5px",
                  }}
                >
                  Search Handler:
                </label>
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Type to search..."
                  style={{
                    width: "100%",
                    padding: "10px",
                    border: "1.5px solid #9370db",
                    borderRadius: "5px",
                    background: "rgba(147, 112, 219, 0.1)",
                    color: "#f0f0f0",
                    fontSize: "14px",
                    marginBottom: "10px",
                  }}
                />

                <div
                  style={{
                    maxHeight: "200px",
                    overflowY: "auto",
                    border: "1.5px solid #9370db",
                    borderRadius: "5px",
                    background: "rgba(147, 112, 219, 0.05)",
                  }}
                >
                  {filteredHandlers.length === 0 ? (
                    <div
                      style={{
                        padding: "15px",
                        color: "#aaa",
                        textAlign: "center",
                      }}
                    >
                      No handlers found
                    </div>
                  ) : (
                    filteredHandlers.map((handler) => (
                      <div
                        key={handler}
                        onClick={() => {
                          setTargetHandler(handler);
                          setSearchTerm("");
                        }}
                        style={{
                          padding: "12px 15px",
                          cursor: "pointer",
                          background:
                            targetHandler === handler
                              ? "rgba(147, 112, 219, 0.3)"
                              : "transparent",
                          color: "#f0f0f0",
                          borderBottom: "1px solid rgba(147, 112, 219, 0.2)",
                          transition: "background 0.2s",
                        }}
                        onMouseEnter={(e) => {
                          if (targetHandler !== handler) {
                            e.currentTarget.style.background =
                              "rgba(147, 112, 219, 0.15)";
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (targetHandler !== handler) {
                            e.currentTarget.style.background = "transparent";
                          }
                        }}
                      >
                        {handler}
                        {targetHandler === handler && (
                          <span style={{ float: "right", color: "#28a745" }}>
                            ✓
                          </span>
                        )}
                      </div>
                    ))
                  )}
                </div>

                {targetHandler && (
                  <div
                    style={{
                      marginTop: "10px",
                      padding: "10px",
                      background: "rgba(40, 167, 69, 0.1)",
                      border: "1px solid #28a745",
                      borderRadius: "5px",
                      color: "#28a745",
                      fontSize: "0.9em",
                    }}
                  >
                    Selected: <strong>{targetHandler}</strong>
                  </div>
                )}
              </div>
            )}

            <div style={{ marginBottom: "20px" }}>
              <label
                style={{
                  color: "#f0f0f0",
                  display: "block",
                  marginBottom: "5px",
                }}
              >
                New Database Name:
              </label>
              <input
                type="text"
                value={targetDbName}
                onChange={(e) => setTargetDbName(e.target.value)}
                placeholder="Enter new database name"
                style={{
                  width: "100%",
                  padding: "10px",
                  border: "1.5px solid #9370db",
                  borderRadius: "5px",
                  background: "rgba(147, 112, 219, 0.1)",
                  color: "#f0f0f0",
                  fontSize: "14px",
                }}
                required
              />
            </div>

            <div
              style={{
                display: "flex",
                gap: "10px",
                justifyContent: "flex-end",
              }}
            >
              <button
                type="button"
                onClick={onClose}
                disabled={loading}
                style={{
                  padding: "10px 20px",
                  background: "#6c757d",
                  color: "white",
                  border: "none",
                  borderRadius: "5px",
                  cursor: loading ? "not-allowed" : "pointer",
                  fontSize: "14px",
                  opacity: loading ? 0.6 : 1,
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || !targetHandler}
                style={{
                  padding: "10px 20px",
                  background: loading || !targetHandler ? "#ccc" : "#9370db",
                  color: "white",
                  border: "none",
                  borderRadius: "5px",
                  cursor: loading || !targetHandler ? "not-allowed" : "pointer",
                  fontSize: "14px",
                }}
              >
                {loading ? "Converting..." : "Convert"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
export default ConvertDatabaseModal;
