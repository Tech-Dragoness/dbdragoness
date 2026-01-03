import React from "react";

function InsertRowModal({ 
  columns, 
  formData, 
  onInputChange, 
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
          Insert New Row
        </h2>

        <div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
              gap: "15px",
              marginBottom: "30px",
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
                  {col.name}{" "}
                  {((col.pk && !col.autoincrement) ||
                    (col.notnull && !col.autoincrement)) && (
                    <span style={{ color: "#ff6b6b" }}>*</span>
                  )}
                  {col.autoincrement && (
                    <span style={{ color: "#4CAF50", fontSize: "0.85em" }}>
                      {" "}
                      (auto-generated - optional)
                    </span>
                  )}
                  {col.pk && !col.autoincrement && (
                    <span style={{ color: "#ffa726", fontSize: "0.85em" }}>
                      {" "}
                      (primary key - required)
                    </span>
                  )}
                </label>
                <input
                  type={
                    col.type === "INTEGER" || col.type === "REAL"
                      ? "number"
                      : "text"
                  }
                  value={formData[col.name] || ""}
                  onChange={(e) => onInputChange(col.name, e.target.value)}
                  placeholder={col.autoincrement ? "Auto-generated" : ""}
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
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleSubmit(e);
                    }
                  }}
                />
              </div>
            ))}
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
                background: "#9370db",
                color: "white",
                border: "none",
                borderRadius: "8px",
                cursor: "pointer",
                fontWeight: "bold",
                boxShadow: "0 4px 20px rgba(147, 112, 219, 0.5)",
              }}
            >
              Insert Row
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default InsertRowModal;