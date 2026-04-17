import React, { useState, useEffect } from "react";
import axios from "axios";

function ConnectionStringCard({ dbName, handlerName }) {
  const [isOpen, setIsOpen] = useState(false);
  const [connInfo, setConnInfo] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen && !connInfo) {
      fetchConnectionInfo();
    }
  }, [isOpen]);

  const fetchConnectionInfo = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`/api/db/${dbName}/connection_info`);
      if (response.data.success) {
        setConnInfo(response.data);
      }
    } catch (err) {
      console.error("Failed to fetch connection info:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div id={`conn-${dbName}`} style={{ marginBottom: "15px" }}>
      <details
        style={{
          marginBottom: "15px",
          padding: "10px",
          background: "#1e0033e6",
          borderRadius: "4px",
          border: "1px solid #ddd",
        }}
        open={isOpen}
        onToggle={(e) => setIsOpen(e.target.open)}
      >
        <summary
          style={{
            cursor: "pointer",
            fontWeight: "bold",
            background: "#1e0033e6",
            color: "#c0bae7ff",
            padding: "8px",
          }}
        >
          🔗 {dbName} - Connection Info
        </summary>

        {loading && <p>Loading...</p>}

        {connInfo && (
          <div
            style={{
              marginTop: "10px",
              padding: "15px",
              background: "#1e0033e6",
              borderLeft: "3px solid #6a5acd",
            }}
          >
            <p>
              <strong>🔌 Connection String:</strong>
            </p>
            <br></br>
            <code
              style={{
                display: "block",
                background: "black",
                color: "#f8f8f2",
                padding: "10px",
                borderRadius: "4px",
                overflowX: "auto",
                marginBottom: "15px",
              }}
            >
              {connInfo.connection_string}
            </code>

            <p>
              <strong>💻 Test Code:</strong>
            </p>
            <br></br>
            <pre
              style={{
                background: "black",
                color: "#f8f8f2",
                padding: "15px",
                borderRadius: "4px",
                overflowX: "auto",
                fontSize: "0.9em",
              }}
            >
              {connInfo.test_code}
            </pre>

            {connInfo.notes && connInfo.notes.length > 0 && (
              <div
                style={{
                  marginTop: "15px",
                  padding: "10px",
                  background: "#fff3cd",
                  borderLeft: "3px solid #ffc107",
                  borderRadius: "4px",
                }}
              >
                <strong style={{ color: "black" }}>💡 Tips:</strong>
                <ul
                  style={{
                    margin: "5px 0",
                    paddingLeft: "20px",
                    fontSize: "0.9em",
                    color: "black",
                  }}
                >
                  {connInfo.notes.map((note, idx) => (
                    <li key={idx}>{note}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </details>
    </div>
  );
}

export default ConnectionStringCard;
