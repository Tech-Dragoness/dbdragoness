import { useState } from "react";

function ModifyDocumentModal({
  dbName,
  collectionName,
  document,
  primaryKey,
  onClose,
  onSuccess,
}) {
  // Separate primary key from editable fields
  const primaryKeyValue = document[primaryKey];
  const editableFields = Object.entries(document).filter(
    ([key]) => key !== primaryKey
  );

  const [fields, setFields] = useState(
    editableFields.map(([key, value]) => ({
      key,
      value:
        typeof value === "object" && value !== null
          ? JSON.stringify(value, null, 2)
          : String(value),
      originalKey: key,
    }))
  );
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const addField = () => {
    setFields([...fields, { key: "", value: "", originalKey: null }]);
  };

  const removeField = (index) => {
    setFields(fields.filter((_, i) => i !== index));
  };

  const updateField = (index, field, value) => {
    const newFields = [...fields];
    newFields[index][field] = value;
    setFields(newFields);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    // Get valid fields (both key and value filled)
    const validFields = fields.filter((f) => f.key.trim() && f.value.trim());

    if (validFields.length === 0) {
      setError("Cannot save an empty document. Please add at least one field.");
      return;
    }

    // Check for half-filled pairs
    const halfFilled = fields.filter(
      (f) =>
        (f.key.trim() && !f.value.trim()) || (!f.key.trim() && f.value.trim())
    );

    if (halfFilled.length > 0) {
      if (
        !window.confirm(
          "Some pairs are only half-filled. Do you want to proceed and discard them?"
        )
      ) {
        return;
      }
    }

    // Build updated document
    const updatedDoc = {};
    const deletedKeys = [];

    // Track what was deleted
    editableFields.forEach(([originalKey]) => {
      const stillExists = validFields.find(
        (f) => f.originalKey === originalKey || f.key.trim() === originalKey
      );
      if (!stillExists) {
        deletedKeys.push(originalKey);
      }
    });

    // Add valid fields
    validFields.forEach((field) => {
      let value = field.value.trim();

      // Try to parse as JSON first (handles arrays and objects)
      if (
        (value.startsWith("[") && value.endsWith("]")) ||
        (value.startsWith("{") && value.endsWith("}"))
      ) {
        try {
          value = JSON.parse(value);
          updatedDoc[field.key.trim()] = value;
          return;
        } catch (e) {
          // If JSON parse fails, treat as string
        }
      }

      // Type conversion for primitives
      if (value.match(/^-?\d+$/)) {
        value = parseInt(value);
      } else if (value.match(/^-?\d+\.\d+$/)) {
        value = parseFloat(value);
      } else if (value === "true") {
        value = true;
      } else if (value === "false") {
        value = false;
      }

      updatedDoc[field.key.trim()] = value;
    });

    // Mark deleted keys as null for backend
    deletedKeys.forEach((key) => {
      updatedDoc[key] = null;
    });

    setLoading(true);

    try {
      const response = await fetch(
        `/api/collection/${dbName}/${collectionName}/document/${primaryKeyValue}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ document: updatedDoc }),
        }
      );

      const data = await response.json();

      if (data.success) {
        onSuccess();
      } else {
        setError(data.error || "Failed to update document");
      }
    } catch (err) {
      setError("Failed to update document: " + err.message);
    } finally {
      setLoading(false);
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
        backdropFilter: "blur(4px)",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "linear-gradient(135deg, #1e0033, #3a0066)",
          padding: "40px",
          borderRadius: "15px",
          maxWidth: "700px",
          width: "90%",
          maxHeight: "80vh",
          overflowY: "auto",
          border: "2px solid #9370db",
          boxShadow: "0 10px 40px rgba(147, 112, 219, 0.6)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          style={{
            color: "#f0f0f0",
            margin: "0 0 25px 0",
            textAlign: "center",
          }}
        >
          Modify Document in {collectionName}
        </h2>

        {error && (
          <div
            style={{
              background: "rgba(220, 53, 69, 0.2)",
              color: "#ff8a80",
              padding: "12px",
              borderRadius: "8px",
              borderLeft: "4px solid #dc3545",
              marginBottom: "20px",
            }}
          >
            {error}
          </div>
        )}

        <div>
          <div style={{ marginBottom: "25px" }}>
            {/* Read-only primary key field */}
            <div
              style={{
                display: "flex",
                gap: "10px",
                marginBottom: "15px",
                alignItems: "center",
              }}
            >
              <input
                type="text"
                value={primaryKey}
                readOnly
                style={{
                  flex: 1,
                  padding: "14px",
                  border: "1.5px solid #666",
                  borderRadius: "8px",
                  background: "rgba(147, 112, 219, 0.1)",
                  color: "#aaa",
                  fontSize: "16px",
                  cursor: "not-allowed",
                }}
              />
              <input
                type="text"
                value={String(primaryKeyValue)}
                readOnly
                style={{
                  flex: 1,
                  padding: "14px",
                  border: "1.5px solid #666",
                  borderRadius: "8px",
                  background: "rgba(147, 112, 219, 0.1)",
                  color: "#aaa",
                  fontSize: "16px",
                  cursor: "not-allowed",
                }}
              />
            </div>

            {/* Editable fields */}
            {fields.map((field, index) => (
              <div
                key={index}
                style={{
                  display: "flex",
                  gap: "10px",
                  marginBottom: "15px",
                  alignItems: "center",
                }}
              >
                <input
                  type="text"
                  value={field.key}
                  onChange={(e) => updateField(index, "key", e.target.value)}
                  placeholder="Key"
                  disabled={loading}
                  style={{
                    flex: 1,
                    padding: "14px",
                    border: "1.5px solid #9370db",
                    borderRadius: "8px",
                    background: "rgba(147, 112, 219, 0.15)",
                    color: "#f0f0f0",
                    fontSize: "16px",
                  }}
                />
                <input
                  type="text"
                  value={field.value}
                  onChange={(e) => updateField(index, "value", e.target.value)}
                  placeholder="Value"
                  disabled={loading}
                  style={{
                    flex: 1,
                    padding: "14px",
                    border: "1.5px solid #9370db",
                    borderRadius: "8px",
                    background: "rgba(147, 112, 219, 0.15)",
                    color: "#f0f0f0",
                    fontSize: "16px",
                  }}
                />
                <button
                  type="button"
                  onClick={() => removeField(index)}
                  disabled={loading}
                  style={{
                    padding: "10px 15px",
                    background: "#dc3545",
                    color: "white",
                    border: "none",
                    borderRadius: "8px",
                    cursor: loading ? "not-allowed" : "pointer",
                    fontSize: "18px",
                    fontWeight: "bold",
                    opacity: loading ? 0.7 : 1,
                  }}
                >
                  ✕
                </button>
              </div>
            ))}

            <button
              type="button"
              onClick={addField}
              disabled={loading}
              style={{
                padding: "10px 20px",
                background: "#6a5acd",
                color: "white",
                border: "none",
                borderRadius: "8px",
                cursor: loading ? "not-allowed" : "pointer",
                fontWeight: "bold",
                opacity: loading ? 0.7 : 1,
                marginTop: "10px",
              }}
            >
              + Add Field
            </button>
          </div>

          <div
            style={{
              background: "rgba(33, 150, 243, 0.15)",
              padding: "16px",
              borderRadius: "10px",
              borderLeft: "4px solid #2196f3",
              color: "#bbdefb",
              marginBottom: "30px",
              fontSize: "0.95em",
            }}
          >
            <strong>Note:</strong> Removing a field will delete it from the
            document. Renaming a key will delete the old key and create a new
            one.
          </div>

          <div
            style={{ display: "flex", gap: "15px", justifyContent: "flex-end" }}
          >
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              style={{
                padding: "14px 28px",
                background: "#6c757d",
                color: "white",
                border: "none",
                borderRadius: "8px",
                cursor: loading ? "not-allowed" : "pointer",
                fontWeight: "bold",
                opacity: loading ? 0.7 : 1,
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={loading}
              style={{
                padding: "14px 28px",
                background: loading ? "#7b68b5" : "#9370db",
                color: "white",
                border: "none",
                borderRadius: "8px",
                cursor: loading ? "not-allowed" : "pointer",
                fontWeight: "bold",
                boxShadow: loading
                  ? "none"
                  : "0 4px 20px rgba(147, 112, 219, 0.5)",
              }}
            >
              {loading ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ModifyDocumentModal;
