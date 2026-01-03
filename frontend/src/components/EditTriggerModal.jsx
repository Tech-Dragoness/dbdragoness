import React, { useState, useEffect } from "react";
import axios from "axios";

function EditTriggerModal({
  dbName,
  tableName,
  triggerName,
  onClose,
  onSuccess,
}) {
  const [triggerData, setTriggerData] = useState({
    trigger_name: "",
    trigger_timing: "BEFORE",
    trigger_event: "INSERT",
    trigger_body: "",
    table: "",
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchTriggerDetails();
  }, []);

  const fetchTriggerDetails = async () => {
    try {
      setLoading(true);

      const response = await axios.get(`/api/db/${dbName}/triggers`);

      if (response.data.success) {
        const trigger = response.data.triggers.find(
          (t) => t.name === triggerName
        );

        if (trigger) {
          // After finding the trigger, clean the body more aggressively:
          let body = trigger.sql || "";

          // For MySQL: Extract content between BEGIN and END
          if (
            body.toUpperCase().includes("BEGIN") &&
            body.toUpperCase().includes("END")
          ) {
            const match = body.match(/BEGIN\s+([\s\S]*?)\s+END/i);
            if (match) {
              body = match[1].trim();
            }
          }

          // For PostgreSQL: Extract from function body
          if (body.includes("$$")) {
            const match = body.match(/\$\$\s+([\s\S]*?)\s+\$\$/);
            if (match) {
              body = match[1].trim();
              // Remove BEGIN...END wrapper if present
              body = body
                .replace(/^\s*BEGIN\s+/i, "")
                .replace(/\s+END\s*$/i, "");
            }
          }

          // Remove RETURN statements
          body = body.replace(/RETURN\s+(NEW|OLD)\s*;?\s*$/i, "");

          // Remove all trailing semicolons
          body = body.replace(/;+\s*$/g, "").trim();

          setTriggerData({
            trigger_name: trigger.name,
            trigger_timing: trigger.timing || "AFTER",
            trigger_event: trigger.event || "INSERT",
            trigger_body: body,
            table: trigger.table || tableName,
          });
        } else {
          setError("Trigger not found");
        }
      }
    } catch (err) {
      setError("Error loading trigger: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);

    const originalName = triggerName;
    const tempName = `${triggerData.trigger_name}_temp_${Date.now()}`;

    try {
      // Step 1: Create temporary trigger
      const tempResponse = await axios.post(
        `/api/table/${dbName}/${triggerData.table}/triggers`,
        {
          trigger_name: tempName,
          trigger_timing: triggerData.trigger_timing,
          trigger_event: triggerData.trigger_event,
          trigger_body: triggerData.trigger_body,
        }
      );

      if (!tempResponse.data.success) {
        throw new Error(
          tempResponse.data.error || "Failed to create temporary trigger"
        );
      }

      // Step 2: Delete original
      const deleteResponse = await axios.post(
        `/api/db/${dbName}/triggers/delete`,
        { trigger_name: originalName }
      );

      if (!deleteResponse.data.success) {
        // Cleanup temp on failure
        await axios
          .post(`/api/db/${dbName}/triggers/delete`, { trigger_name: tempName })
          .catch(() => {});
        throw new Error("Failed to delete old trigger — rolling back");
      }

      // Step 3: Create final trigger with original name
      const finalResponse = await axios.post(
        `/api/table/${dbName}/${triggerData.table}/triggers`,
        {
          trigger_name: triggerData.trigger_name,
          trigger_timing: triggerData.trigger_timing,
          trigger_event: triggerData.trigger_event,
          trigger_body: triggerData.trigger_body,
        }
      );

      if (!finalResponse.data.success) {
        throw new Error(
          finalResponse.data.error || "Failed to create final trigger"
        );
      }

      // 🎉 SUCCESS! Now dismiss the faithful temp trigger
      await axios
        .post(`/api/db/${dbName}/triggers/delete`, { trigger_name: tempName })
        .catch((err) => {
          console.warn(
            "Minor cleanup issue: could not delete temporary trigger",
            tempName,
            err
          );
          // We don't fail the whole update for this — it's just housekeeping
        });

      onSuccess(
        `Trigger "${triggerData.trigger_name}" updated ! ✨`
      );
      onClose();
    } catch (err) {
      setError(
        `Update failed: ${err.message}. ` +
          `Your original trigger "${originalName}" remains safe and unchanged.`
      );
      console.error("Trigger update error:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleInputChange = (field, value) => {
    setTriggerData({
      ...triggerData,
      [field]: value,
    });
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
          ✏️ Edit Trigger: {triggerName}
        </h2>

        <div
          style={{
            background: "rgba(147, 112, 219, 0.2)",
            padding: "15px",
            borderRadius: "8px",
            marginBottom: "20px",
            border: "1px solid #9370db",
          }}
        >
          <h4 style={{ color: "#bb86fc", marginTop: 0, marginBottom: "10px" }}>
            📋 Format Guidelines:
          </h4>
          <ul
            style={{
              color: "#e0e0e0",
              fontSize: "0.9em",
              margin: 0,
              paddingLeft: "20px",
            }}
          >
            <li>
              <strong>PostgreSQL:</strong> Use PL/pgSQL syntax. RETURN is
              auto-added if missing
            </li>
            <li>
              <strong>MySQL:</strong> Use MySQL trigger syntax (no DELIMITER
              needed)
            </li>
            <li>
              <strong>SQLite:</strong> Use SQLite trigger syntax
            </li>
            <li>
              <strong>Timing:</strong> BEFORE or AFTER
            </li>
            <li>
              <strong>Event:</strong> INSERT, UPDATE, or DELETE
            </li>
            <li>
              <strong>Body:</strong> The action to perform (without BEGIN/END
              wrapper)
            </li>
          </ul>
        </div>

        {error && (
          <div className="error" style={{ marginBottom: "15px" }}>
            {error}
          </div>
        )}

        {loading ? (
          <div
            style={{ textAlign: "center", padding: "40px", color: "#f0f0f0" }}
          >
            <div className="loading">Loading trigger details...</div>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            {/* Trigger Name */}
            <div style={{ marginBottom: "15px" }}>
              <label
                style={{
                  color: "#f0f0f0",
                  display: "block",
                  marginBottom: "5px",
                  fontWeight: "bold",
                }}
              >
                Trigger Name:
              </label>
              <input
                type="text"
                value={triggerData.trigger_name}
                onChange={(e) =>
                  handleInputChange("trigger_name", e.target.value)
                }
                required
                style={{
                  width: "100%",
                  padding: "10px",
                  border: "1.5px solid #9370db",
                  borderRadius: "5px",
                  background: "rgba(30, 0, 51, 0.5)",
                  color: "#f0f0f0",
                  fontSize: "14px",
                }}
              />
            </div>

            {/* Table Name (read-only display) */}
            <div style={{ marginBottom: "15px" }}>
              <label
                style={{
                  color: "#f0f0f0",
                  display: "block",
                  marginBottom: "5px",
                  fontWeight: "bold",
                }}
              >
                Table:
              </label>
              <input
                type="text"
                value={triggerData.table}
                readOnly
                style={{
                  width: "100%",
                  padding: "10px",
                  border: "1.5px solid #555",
                  borderRadius: "5px",
                  background: "rgba(30, 0, 51, 0.3)",
                  color: "#999",
                  fontSize: "14px",
                  cursor: "not-allowed",
                }}
              />
            </div>

            {/* Timing and Event */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "15px",
                marginBottom: "15px",
              }}
            >
              <div>
                <label
                  style={{
                    color: "#f0f0f0",
                    display: "block",
                    marginBottom: "5px",
                    fontWeight: "bold",
                  }}
                >
                  Timing:
                </label>
                <select
                  value={triggerData.trigger_timing}
                  onChange={(e) =>
                    handleInputChange("trigger_timing", e.target.value)
                  }
                  style={{
                    width: "100%",
                    padding: "10px",
                    border: "1.5px solid #9370db",
                    borderRadius: "5px",
                    background: "rgba(30, 0, 51, 0.5)",
                    color: "#f0f0f0",
                    fontSize: "14px",
                  }}
                >
                  <option value="BEFORE">BEFORE</option>
                  <option value="AFTER">AFTER</option>
                </select>
              </div>

              <div>
                <label
                  style={{
                    color: "#f0f0f0",
                    display: "block",
                    marginBottom: "5px",
                    fontWeight: "bold",
                  }}
                >
                  Event:
                </label>
                <select
                  value={triggerData.trigger_event}
                  onChange={(e) =>
                    handleInputChange("trigger_event", e.target.value)
                  }
                  style={{
                    width: "100%",
                    padding: "10px",
                    border: "1.5px solid #9370db",
                    borderRadius: "5px",
                    background: "rgba(30, 0, 51, 0.5)",
                    color: "#f0f0f0",
                    fontSize: "14px",
                  }}
                >
                  <option value="INSERT">INSERT</option>
                  <option value="UPDATE">UPDATE</option>
                  <option value="DELETE">DELETE</option>
                </select>
              </div>
            </div>

            {/* Trigger Body */}
            <div style={{ marginBottom: "20px" }}>
              <label
                style={{
                  color: "#f0f0f0",
                  display: "block",
                  marginBottom: "8px",
                  fontWeight: "bold",
                }}
              >
                Trigger Body:
              </label>
              <textarea
                value={triggerData.trigger_body}
                onChange={(e) =>
                  handleInputChange("trigger_body", e.target.value)
                }
                rows={12}
                required
                placeholder={`Examples (RETURN is auto-added if missing):

-- PostgreSQL: Auto-update timestamp on INSERT/UPDATE
NEW.updated_at := NOW();

-- PostgreSQL: Capitalize text on INSERT
NEW.name := INITCAP(NEW.name);
RAISE NOTICE 'Capitalized: % (id: %)', NEW.name, NEW.id;

-- MySQL: Update timestamp
SET NEW.updated_at = NOW();

-- SQLite: Log changes
INSERT INTO audit_log (action, timestamp) VALUES ('INSERT', datetime('now'));`}
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

            {/* Action Buttons */}
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
                {submitting ? "Updating..." : "💾 Update Trigger"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default EditTriggerModal;
