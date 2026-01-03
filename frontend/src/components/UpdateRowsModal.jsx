import React from "react";

function UpdateRowsModal({ 
  columns, 
  updateFormData, 
  updateCondition,
  onInputChange, 
  onConditionChange,
  onSubmit, 
  onClose 
}) {
  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(e);
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
          border: "2px solid #1e9530",
          boxShadow: "0 10px 40px rgba(30, 149, 48, 0.6)",
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
          Update Rows
        </h2>

        <div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
              gap: "15px",
              marginBottom: "20px",
            }}
          >
            {columns.map((col) => (
              <div key={col.name}>
                <label
                  style={{
                    display: "block",
                    marginBottom: "5px",
                    color: "#f0f0f0",
                    fontWeight: "bold",
                  }}
                >
                  {col.name}
                </label>
                <input
                  type={
                    col.type === "INTEGER" || col.type === "REAL"
                      ? "number"
                      : "text"
                  }
                  value={updateFormData[col.name] || ""}
                  onChange={(e) => onInputChange(col.name, e.target.value)}
                  style={{
                    width: "100%",
                    padding: "10px",
                    border: "1.5px solid #9370db",
                    borderRadius: "8px",
                    background: "rgba(147, 112, 219, 0.15)",
                    color: "#f0f0f0",
                    fontSize: "14px",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            ))}
          </div>

          <div style={{ marginBottom: "25px" }}>
            <label
              style={{
                display: "block",
                marginBottom: "10px",
                color: "#f0f0f0",
                fontWeight: "bold",
              }}
            >
              WHERE Clause (Required):
            </label>
            <input
              type="text"
              value={updateCondition}
              onChange={(e) => onConditionChange(e.target.value)}
              placeholder="e.g., id = 1 or name = 'Alice'"
              style={{
                width: "100%",
                padding: "12px",
                border: "1.5px solid #9370db",
                borderRadius: "8px",
                background: "rgba(147, 112, 219, 0.15)",
                color: "#f0f0f0",
                fontSize: "14px",
                boxSizing: "border-box",
              }}
            />
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
            Leave fields empty to keep their current values. Only non-empty
            fields will be updated.
          </div>

          <div
            style={{
              display: "flex",
              gap: "15px",
              justifyContent: "flex-end",
            }}
          >
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: "14px 28px",
                background: "#6c757d",
                color: "white",
                border: "none",
                borderRadius: "8px",
                cursor: "pointer",
                fontWeight: "bold",
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              style={{
                padding: "14px 28px",
                background: "#1e9530",
                color: "white",
                border: "none",
                borderRadius: "8px",
                cursor: "pointer",
                fontWeight: "bold",
                boxShadow: "0 4px 20px rgba(30, 149, 48, 0.5)",
              }}
            >
              Update Rows
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default UpdateRowsModal;