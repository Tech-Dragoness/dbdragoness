import React from "react";

function DeleteRowsModal({ 
  deleteCondition,
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
          maxWidth: "600px",
          width: "90%",
          border: "2px solid #dc3545",
          boxShadow: "0 10px 40px rgba(220, 53, 69, 0.6)",
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
          Delete Rows
        </h2>

        <div
          style={{
            background: "rgba(220, 53, 69, 0.2)",
            color: "#ff8a80",
            padding: "16px",
            borderRadius: "10px",
            borderLeft: "4px solid #dc3545",
            marginBottom: "25px",
            fontSize: "0.95em",
          }}
        >
          ⚠️ Warning: This will permanently delete all rows matching your
          condition. This action cannot be undone.
        </div>

        <div>
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
              value={deleteCondition}
              onChange={(e) => onConditionChange(e.target.value)}
              placeholder="e.g., id > 10 or status = 'inactive'"
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
                background: "#dc3545",
                color: "white",
                border: "none",
                borderRadius: "8px",
                cursor: "pointer",
                fontWeight: "bold",
                boxShadow: "0 4px 20px rgba(220, 53, 69, 0.5)",
              }}
            >
              Delete Rows
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default DeleteRowsModal;