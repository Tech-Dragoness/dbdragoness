import React, { useState } from "react";
import axios from "axios";

function ImportExportTab({ dbName, tableName, isTable }) {
  const [mode, setMode] = useState("export"); // 'export' or 'import'
  const [format, setFormat] = useState("json"); // 'json' or 'sql'
  const [importContent, setImportContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [exportedContent, setExportedContent] = useState("");

  const handleExport = async () => {
    setError("");
    setMessage("");
    setLoading(true);

    try {
      const endpoint = isTable
        ? `/api/db/${dbName}/table/${tableName}/export`
        : `/api/db/${dbName}/export`;

      const response = await axios.post(endpoint, { format });

      if (response.data.success) {
        setExportedContent(response.data.content);
        setMessage("Export generated successfully!");

        // Trigger download
        const blob = new Blob([response.data.content], {
          type: format === "sql" ? "text/plain" : "application/json",
        });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = response.data.filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        setError(response.data.error || "Export failed");
      }
    } catch (err) {
      setError("Export failed: " + (err.response?.data?.error || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async () => {
    setError("");
    setMessage("");

    if (!importContent.trim()) {
      setError("Please provide content to import");
      return;
    }

    if (
      !window.confirm(
        `⚠️ WARNING: This will modify your ${
          isTable ? "table" : "database"
        }. Are you sure?`
      )
    ) {
      return;
    }

    setLoading(true);

    try {
      const endpoint = `/api/db/${dbName}/import`;

      const response = await axios.post(endpoint, {
        content: importContent,
        format,
      });

      if (response.data.success) {
        setMessage(
          response.data.message ||
            "Import completed successfully! Refreshing..."
        );
        setImportContent("");

        // Refresh the page after 2 seconds to show imported data
        setTimeout(() => {
          window.location.reload();
        }, 2000);
      } else {
        setError(response.data.error || "Import failed");
      }
    } catch (err) {
      setError("Import failed: " + (err.response?.data?.error || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Check file size (max 10MB)
    const maxSize = 10 * 1024 * 1024; // 10MB
    if (file.size > maxSize) {
      setError("File too large. Maximum size is 10MB.");
      return;
    }

    setError("");
    setMessage(`Loading file: ${file.name}...`);

    const reader = new FileReader();
    reader.onload = (event) => {
      setImportContent(event.target.result);
      setMessage(
        `File loaded: ${file.name} (${(file.size / 1024).toFixed(2)} KB)`
      );
    };
    reader.onerror = () => {
      setError("Failed to read file. Please try again.");
    };
    reader.readAsText(file);
  };

  return (
    <div>
      <h3 style={{ color: "#f0f0f0", marginBottom: "20px" }}>
        📦 Import/Export{" "}
        {isTable ? `Table: ${tableName}` : `Database: ${dbName}`}
      </h3>

      {error && <div className="error">{error}</div>}
      {message && <div className="success">{message}</div>}

      {/* Mode Selection */}
      <div style={{ marginBottom: "20px" }}>
        <button
          onClick={() => setMode("export")}
          style={{
            padding: "10px 20px",
            background: mode === "export" ? "#4b0082" : "#6c757d",
            color: "white",
            border: "none",
            borderRadius: "5px",
            cursor: "pointer",
            marginRight: "10px",
          }}
        >
          📤 Export
        </button>
        <button
          onClick={() => setMode("import")}
          style={{
            padding: "10px 20px",
            background: mode === "import" ? "#4b0082" : "#6c757d",
            color: "white",
            border: "none",
            borderRadius: "5px",
            cursor: "pointer",
          }}
        >
          📥 Import
        </button>
      </div>

      {/* Format Selection */}
      <div style={{ marginBottom: "20px" }}>
        <label style={{ color: "#f0f0f0", marginRight: "10px" }}>Format:</label>
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value)}
          style={{
            padding: "8px",
            border: "1.5px solid #9370db",
            borderRadius: "5px",
            background: "rgba(30, 0, 51, 0.5)",
            color: "#f0f0f0",
          }}
        >
          <option value="json">JSON (Universal)</option>
          <option value="sql">SQL (Native)</option>
        </select>
      </div>

      {/* Export Mode */}
      {mode === "export" && (
        <div>
          <p style={{ color: "#ccc", fontSize: "0.9em", marginBottom: "15px" }}>
            Export your {isTable ? "table" : "database"} to{" "}
            {format.toUpperCase()} format.
            {format === "json" &&
              " JSON format is universal and can be imported into any database type."}
            {format === "sql" &&
              " SQL format uses native SQL syntax specific to your database."}
          </p>

          <button
            onClick={handleExport}
            disabled={loading}
            style={{
              padding: "12px 30px",
              background: loading ? "#6c757d" : "#6a5acd",
              color: "white",
              border: "none",
              borderRadius: "5px",
              cursor: loading ? "not-allowed" : "pointer",
              fontWeight: "bold",
            }}
          >
            {loading ? "⏳ Generating..." : "📤 Export"}
          </button>

          {exportedContent && (
            <div style={{ marginTop: "20px" }}>
              <h4 style={{ color: "#f0f0f0" }}>Preview:</h4>
              <textarea
                value={exportedContent}
                readOnly
                rows={15}
                style={{
                  width: "100%",
                  padding: "10px",
                  border: "1.5px solid #9370db",
                  borderRadius: "5px",
                  background: "rgba(147, 112, 219, 0.1)",
                  color: "#f0f0f0",
                  fontSize: "13px",
                  fontFamily: "monospace",
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* Import Mode */}
      {mode === "import" && (
        <div>
          <p style={{ color: "#ccc", fontSize: "0.9em", marginBottom: "15px" }}>
            ⚠️ Import will modify your {isTable ? "table" : "database"}. All
            operations are done as a transaction - if anything fails, changes
            will be rolled back.
          </p>

          <div style={{ marginBottom: "15px" }}>
            <label
              style={{
                color: "#f0f0f0",
                display: "block",
                marginBottom: "5px",
              }}
            >
              Upload File:
            </label>
            <input
              type="file"
              accept={format === "sql" ? ".sql" : ".json"}
              onChange={handleFileUpload}
              style={{
                padding: "8px",
                color: "#f0f0f0",
                background: "rgba(30, 0, 51, 0.5)",
                border: "1.5px solid #9370db",
                borderRadius: "5px",
              }}
            />
          </div>

          <div style={{ marginBottom: "15px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "5px",
              }}
            >
              <label style={{ color: "#f0f0f0" }}>Or paste content:</label>
              {importContent && (
                <button
                  onClick={() => setImportContent("")}
                  style={{
                    padding: "4px 12px",
                    background: "#6c757d",
                    color: "white",
                    border: "none",
                    borderRadius: "3px",
                    cursor: "pointer",
                    fontSize: "0.85em",
                  }}
                >
                  Clear
                </button>
              )}
            </div>
            <textarea
              value={importContent}
              onChange={(e) => setImportContent(e.target.value)}
              rows={15}
              placeholder={`Paste your ${format.toUpperCase()} content here...`}
              style={{
                width: "100%",
                padding: "10px",
                border: "1.5px solid #9370db",
                borderRadius: "5px",
                background: "rgba(147, 112, 219, 0.1)",
                color: "#f0f0f0",
                fontSize: "13px",
                fontFamily: "monospace",
              }}
            />
            {importContent && (
              <div
                style={{ fontSize: "0.8em", color: "#999", marginTop: "5px" }}
              >
                Content size: {(importContent.length / 1024).toFixed(2)} KB
              </div>
            )}
          </div>

          <button
            onClick={handleImport}
            disabled={loading || !importContent.trim()}
            style={{
              padding: "12px 30px",
              background:
                loading || !importContent.trim() ? "#6c757d" : "#dc3545",
              color: "white",
              border: "none",
              borderRadius: "5px",
              cursor:
                loading || !importContent.trim() ? "not-allowed" : "pointer",
              fontWeight: "bold",
            }}
          >
            {loading ? "⏳ Importing..." : "📥 Import"}
          </button>
        </div>
      )}
    </div>
  );
}
export default ImportExportTab;
