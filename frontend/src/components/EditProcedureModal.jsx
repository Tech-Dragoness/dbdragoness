import React, { useState, useEffect } from "react";
import axios from "axios";

function EditProcedureModal({ dbName, procedureName, procedureType, onClose, onSuccess }) {
  const [procedureCode, setProcedureCode] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchProcedureCode();
  }, []);

  const fetchProcedureCode = async () => {
    try {
      setLoading(true);
      const response = await axios.get(
        `/api/db/${dbName}/procedure/${procedureName}/code`
      );

      if (response.data.success) {
        setProcedureCode(response.data.code);
      } else {
        setError("Failed to load procedure code");
      }
    } catch (err) {
      setError("Error loading procedure: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      // First, drop the existing procedure/function
      const dropResponse = await axios.post(`/api/db/${dbName}/procedure/drop`, {
        procedure_name: procedureName,
        is_function: procedureType === "FUNCTION",
      });

      if (!dropResponse.data.success) {
        throw new Error("Failed to drop existing procedure");
      }

      // Then create the new version
      const createResponse = await axios.post(
        `/api/db/${dbName}/procedures/execute`,
        {
          procedure_code: procedureCode,
        }
      );

      if (createResponse.data.success) {
        onSuccess("Procedure updated successfully");
        onClose();
      } else {
        setError(createResponse.data.error || "Failed to update procedure");
      }
    } catch (err) {
      setError(
        "Failed to update procedure: " +
          (err.response?.data?.error || err.message)
      );
    } finally {
      setSubmitting(false);
    }
  };

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
        padding: "20px",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "linear-gradient(135deg, #1e0033, #3a0066)",
          padding: "30px",
          borderRadius: "15px",
          maxWidth: "900px",
          width: "95%",
          maxHeight: "90vh",
          overflowY: "auto",
          border: "2px solid #9370db",
          boxShadow: "0 10px 40px rgba(147, 112, 219, 0.6)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ color: "#f0f0f0", marginBottom: "10px" }}>
          ✏️ Edit {procedureType}: {procedureName}
        </h2>
        
        <div style={{
          background: "rgba(147, 112, 219, 0.2)",
          padding: "15px",
          borderRadius: "8px",
          marginBottom: "20px",
          border: "1px solid #9370db"
        }}>
          <h4 style={{ color: "#bb86fc", marginTop: 0, marginBottom: "10px" }}>
            📝 Format Guidelines:
          </h4>
          <ul style={{ color: "#e0e0e0", fontSize: "0.9em", margin: 0, paddingLeft: "20px" }}>
            <li><strong>MySQL:</strong> Include DELIMITER statements</li>
            <li><strong>PostgreSQL:</strong> Functions only (no procedures)</li>
            <li><strong>DuckDB:</strong> Functions with CREATE OR REPLACE</li>
            <li>Use the <strong>exact same format</strong> as when creating</li>
            <li>The old procedure will be dropped before creating the new version</li>
          </ul>
        </div>

        {error && (
          <div className="error" style={{ marginBottom: "15px" }}>
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: "center", padding: "40px", color: "#f0f0f0" }}>
            <div className="loading">Loading procedure code...</div>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: "20px" }}>
              <label
                style={{
                  color: "#f0f0f0",
                  display: "block",
                  marginBottom: "8px",
                  fontWeight: "bold"
                }}
              >
                Procedure Code:
              </label>
              <textarea
                value={procedureCode}
                onChange={(e) => setProcedureCode(e.target.value)}
                rows={20}
                required
                placeholder={`Example for MySQL:

DELIMITER $$
CREATE PROCEDURE GetTopStudents()
BEGIN
    SELECT name, marks FROM students WHERE marks > 85;
END$$
DELIMITER ;`}
                style={{
                  width: "100%",
                  padding: "12px",
                  border: "1.5px solid #9370db",
                  borderRadius: "5px",
                  background: "rgba(30, 0, 51, 0.5)",
                  color: "#f0f0f0",
                  fontSize: "13px",
                  fontFamily: "monospace",
                  lineHeight: "1.5",
                  resize: "vertical",
                }}
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
                disabled={submitting}
                style={{
                  padding: "10px 20px",
                  background: "#6c757d",
                  color: "white",
                  border: "none",
                  borderRadius: "8px",
                  cursor: submitting ? "not-allowed" : "pointer",
                  opacity: submitting ? 0.6 : 1,
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                style={{
                  padding: "10px 20px",
                  background: submitting ? "#6c757d" : "#9370db",
                  color: "white",
                  border: "none",
                  borderRadius: "8px",
                  cursor: submitting ? "not-allowed" : "pointer",
                  fontWeight: "bold",
                }}
              >
                {submitting ? "Updating..." : "💾 Update Procedure"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default EditProcedureModal;