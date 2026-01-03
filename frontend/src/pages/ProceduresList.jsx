import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import Sidebar from "../components/Sidebar";
import EditProcedureModal from "../components/EditProcedureModal";

function ProceduresList() {
  const { dbName } = useParams();
  const navigate = useNavigate();

  const [procedures, setProcedures] = useState([]);
  const [supportsProcedures, setSupportsProcedures] = useState(false);
  const [dbType, setDbType] = useState("sql");
  const [handlerName, setHandlerName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  // Execution results state
  const [queryResult, setQueryResult] = useState(null);
  const [executedProcedureName, setExecutedProcedureName] = useState("");

  // Edit modal state
  const [showEditProcedureModal, setShowEditProcedureModal] = useState(false);
  const [editingProcedure, setEditingProcedure] = useState(null);

  useEffect(() => {
    fetchProcedures();
  }, [dbName]);

  const fetchProcedures = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/api/db/${dbName}/procedures`);

      if (response.data.success) {
        setProcedures(response.data.procedures);
        setSupportsProcedures(response.data.supports_procedures);
        setDbType(response.data.db_type);
        setHandlerName(response.data.handler);
      } else {
        setError(response.data.error || "Failed to fetch procedures");
      }
    } catch (err) {
      console.error("Failed to fetch procedures:", err);
      setError("Failed to connect to server");
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteSpecificProcedure = async (procedureName) => {
    setError("");
    setMessage("");
    setQueryResult(null);
    setExecutedProcedureName(procedureName);

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

        // Scroll to results
        setTimeout(() => {
          document.getElementById("execution-results")?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        }, 100);
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

  const handleViewCode = async (procedureName, procedureType) => {
    try {
      const response = await axios.get(
        `/api/db/${dbName}/procedure/${procedureName}/code`
      );

      if (response.data.success) {
        // Create modal
        const modal = document.createElement("div");
        modal.style.cssText =
          "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;";

        modal.innerHTML = `
        <div style="background:white;padding:30px;border-radius:15px;max-width:900px;width:100%;max-height:90%;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,0.3);">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;border-bottom:2px solid #6a5acd;padding-bottom:15px;">
            <h2 style="margin:0;color:#4b0082;">${procedureType}: ${procedureName}</h2>
            <button id="copyBtn" title="Copy to clipboard"
              style="background:#6a5acd;color:white;padding:8px 15px;border:none;border-radius:5px;cursor:pointer;font-size:14px;">
              📋 Copy
            </button>
          </div>
          <pre id="procedure-code" style="background:#f5f5f5;color:black; padding:20px;border-radius:8px;overflow-x:auto;font-family:'Courier New',monospace;font-size:13px;line-height:1.6;border:1px solid #ddd;">${escapeHtml(
            response.data.code
          )}</pre>
          <div style="text-align:right;margin-top:20px;">
            <button id="closeBtn" 
              style="background:#6c757d;color:white;padding:10px 25px;border:none;border-radius:8px;cursor:pointer;font-size:15px;">
              Close
            </button>
          </div>
        </div>
      `;

        document.body.appendChild(modal);

        // Add event listeners
        document.getElementById("closeBtn").onclick = () => modal.remove();
        modal.onclick = (e) => {
          if (e.target === modal) modal.remove();
        };
        document.getElementById("copyBtn").onclick = () => {
          const code = document.getElementById("procedure-code").textContent;
          navigator.clipboard.writeText(code).then(() => {
            const btn = document.getElementById("copyBtn");
            const originalText = btn.textContent;
            btn.textContent = "✅ Copied!";
            btn.style.background = "#4caf50";
            setTimeout(() => {
              btn.textContent = originalText;
              btn.style.background = "#6a5acd";
            }, 2000);
          });
        };
      } else {
        alert("❌ Failed to load code: " + response.data.error);
      }
    } catch (err) {
      alert("❌ Error: " + err.message);
    }
  };

  const handleDropProcedure = async (procedureName, isFunction) => {
    const type = isFunction ? "function" : "procedure";
    if (!window.confirm(`Delete ${type} ${procedureName}?`)) {
      return;
    }

    try {
      const response = await axios.post(`/api/db/${dbName}/procedure/drop`, {
        procedure_name: procedureName,
        is_function: isFunction,
      });

      if (response.data.success) {
        setMessage(response.data.message);
        fetchProcedures();
      } else {
        setError(response.data.error || "Failed to drop procedure");
      }
    } catch (err) {
      setError(
        "Failed to drop procedure: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  const escapeHtml = (text) => {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  };

  if (loading) {
    return (
      <>
        <Sidebar dbType={dbType} handlerName={handlerName} />
        <div className="center">
          <div className="loading">Loading procedures...</div>
        </div>
      </>
    );
  }

  return (
    <>
      <Sidebar dbType={dbType} handlerName={handlerName} />
      <div className="center">
        <h2 style={{ color: "#f0f0f0" }}>
          🔧 Stored Procedures & Functions in {dbName}
        </h2>
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

        {/* EXECUTION RESULTS TABLE - Only visible when queryResult exists */}
        {queryResult && (
          <div
            id="execution-results"
            style={{ marginTop: "20px", marginBottom: "30px" }}
          >
            <h3 style={{ color: "#f0f0f0" }}>
              📊 Execution Results: {executedProcedureName}
            </h3>
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
                    padding: "20px",
                    background: "#f8f8f8",
                    borderRadius: "8px",
                  }}
                >
                  Procedure executed successfully. No results returned.
                </p>
              )
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
            <button
              onClick={() => {
                setQueryResult(null);
                setExecutedProcedureName("");
              }}
              style={{
                background: "#6c757d",
                color: "white",
                padding: "8px 16px",
                border: "none",
                borderRadius: "5px",
                cursor: "pointer",
                marginTop: "10px",
              }}
            >
              Clear Results
            </button>
          </div>
        )}

        {procedures.length > 0 ? (
          <div style={{ overflowX: "auto", width: "95%", margin: "20px auto" }}>
            <table
              className="result-table"
              style={{ width: "100%", minWidth: "900px" }}
            >
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Created</th>
                  <th>Last Modified</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {procedures.map((proc, idx) => (
                  <tr key={idx}>
                    <td>
                      <strong>{proc.name}</strong>
                    </td>
                    <td>
                      <span
                        style={{
                          padding: "4px 8px",
                          borderRadius: "4px",
                          fontSize: "12px",
                          fontWeight: "bold",
                          background:
                            proc.type === "PROCEDURE" ? "#e3f2fd" : "#f3e5f5",
                          color:
                            proc.type === "PROCEDURE" ? "#1976d2" : "#7b1fa2",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {proc.type}
                      </span>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {proc.created || "N/A"}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {proc.modified || "N/A"}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button
                        onClick={() =>
                          handleExecuteSpecificProcedure(proc.name)
                        }
                        style={{
                          background: "#28a745",
                          color: "white",
                          padding: "6px 12px",
                          border: "none",
                          borderRadius: "4px",
                          cursor: "pointer",
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
                          color: "white",
                          padding: "6px 12px",
                          border: "none",
                          borderRadius: "4px",
                          cursor: "pointer",
                          marginRight: "5px",
                          fontSize: "0.9em",
                        }}
                      >
                        ✏️ Edit
                      </button>
                      <button
                        onClick={() => handleViewCode(proc.name, proc.type)}
                        style={{
                          background: "#6a5acd",
                          color: "white",
                          padding: "6px 12px",
                          border: "none",
                          borderRadius: "4px",
                          cursor: "pointer",
                          marginRight: "5px",
                        }}
                      >
                        📄 View
                      </button>
                      <button
                        onClick={() =>
                          handleDropProcedure(
                            proc.name,
                            proc.type === "FUNCTION"
                          )
                        }
                        style={{
                          background: "#dc3545",
                          color: "white",
                          padding: "6px 12px",
                          border: "none",
                          borderRadius: "4px",
                          cursor: "pointer",
                        }}
                      >
                        🗑️ Drop
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div
            style={{
              textAlign: "center",
              padding: "40px",
              background: "#f8f8f8",
              borderRadius: "10px",
              margin: "20px auto",
              maxWidth: "600px",
            }}
          >
            <p style={{ fontSize: "3em", margin: 0 }}>🔍</p>
            <h3 style={{ color: "#666" }}>No Procedures or Functions Found</h3>
            <p style={{ color: "#999" }}>
              Create your first stored procedure using the Procedures tab in any
              table view.
            </p>
          </div>
        )}
      </div>

      {/* Edit Procedure Modal */}
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
    </>
  );
}

export default ProceduresList;
