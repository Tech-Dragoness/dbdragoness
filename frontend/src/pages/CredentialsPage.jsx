import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import axios from "axios";

function CredentialsPage() {
  const { handlerName } = useParams();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [dbType, setDbType] = useState("sql");

  useEffect(() => {
    fetchDbType();
  }, []);

  const fetchDbType = async () => {
    try {
      const response = await axios.get("/api/current_state");
      if (response.data.success) {
        setDbType(response.data.db_type);
      }
    } catch (err) {
      console.error("Failed to fetch db type:", err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      // ✅ CHANGED: Use JSON API endpoint instead of form-urlencoded
      const response = await axios.post(
        `/api/handler_credentials/${handlerName}`, // ✅ NEW API ROUTE
        {
          username: username,
          password: password,
        },
        {
          headers: {
            "Content-Type": "application/json", // ✅ JSON instead of form data
          },
        }
      );

      console.log("✅ Credentials response:", response.data);

      if (response.data.success) {
        setSuccess(response.data.message);

        // Navigate to home WITHOUT reload
        setTimeout(() => {
          navigate("/", { replace: true, state: { credentialsUpdated: true } });
        }, 1500);
      } else {
        setError(response.data.message);
        setPassword("");
      }
    } catch (err) {
      console.error("Credentials error:", err);
      setError(
        err.response?.data?.message || err.message || "Connection failed"
      );
      setPassword("");
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    if (
      window.confirm(
        "Cancel credential setup? You will be returned to the home page."
      )
    ) {
      navigate("/", { replace: true });
    }
  };

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      {/* ←←← SIDEBAR ←←← */}
      <Sidebar />

      {/* ←←← MAIN CONTENT — FULL HEIGHT, NO OVERLAP ←←← */}
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: "600px",
            padding: "40px 20px",
            background: "rgba(30, 0, 51, 0.7)",
            borderRadius: "16px",
            boxShadow: "0 10px 40px rgba(147, 112, 219, 0.4)",
            backdropFilter: "blur(10px)",
            border: "1px solid rgba(147, 112, 219, 0.3)",
          }}
        >
          <h2
            style={{
              color: "#bb86fc",
              textAlign: "center",
              fontSize: "2em",
              marginBottom: "10px",
            }}
          >
            {handlerName} Connection Setup
          </h2>

          <p
            style={{ textAlign: "center", color: "#ddd", marginBottom: "30px" }}
          >
            DBDragoness needs your {handlerName} credentials.
            <br />
            They will be stored securely in your system's keyring.
          </p>

          {/* Info Box */}
          <div
            style={{
              background: "rgba(33, 150, 243, 0.2)",
              borderLeft: "4px solid #2196f3",
              padding: "15px",
              marginBottom: "25px",
              borderRadius: "8px",
              color: "#bbdefb",
            }}
          >
            <strong>Secure Storage:</strong>
            <br />
            <small>
              • Windows → Credential Manager
              <br />
              • macOS → Keychain
              <br />• Linux → Secret Service
            </small>
          </div>

          {/* Error / Success */}
          {error && (
            <div
              style={{
                background: "#ffebee",
                color: "#c62828",
                padding: "12px",
                borderRadius: "8px",
                marginBottom: "20px",
                borderLeft: "4px solid #f44336",
              }}
            >
              ✗ {error}
            </div>
          )}
          {success && (
            <div
              style={{
                background: "#e8f5e9",
                color: "#2e7d32",
                padding: "12px",
                borderRadius: "8px",
                marginBottom: "20px",
                borderLeft: "4px solid #4caf50",
              }}
            >
              ✓ {success}
            </div>
          )}

          {/* Form */}
          <form
            onSubmit={handleSubmit}
            style={{
              background: "rgba(255,255,255,0.95)",
              padding: "30px",
              borderRadius: "12px",
              boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
            }}
          >
            <div style={{ marginBottom: "20px" }}>
              <label
                style={{
                  display: "block",
                  marginBottom: "8px",
                  fontWeight: "bold",
                  color: "#333",
                }}
              >
                Username:
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter username"
                required
                disabled={loading}
                style={{
                  width: "100%",
                  padding: "12px",
                  border: "2px solid #ddd",
                  borderRadius: "8px",
                  fontSize: "16px",
                }}
              />
            </div>

            <div style={{ marginBottom: "30px" }}>
              <label
                style={{
                  display: "block",
                  marginBottom: "8px",
                  fontWeight: "bold",
                  color: "#333",
                }}
              >
                Password:
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Leave blank if none"
                disabled={loading}
                style={{
                  width: "100%",
                  padding: "12px",
                  border: "2px solid #ddd",
                  borderRadius: "8px",
                  fontSize: "16px",
                }}
              />
            </div>

            <div style={{ display: "flex", gap: "12px" }}>
              <button
                type="button"
                onClick={handleCancel}
                disabled={loading}
                style={{
                  flex: 1,
                  padding: "14px",
                  background: "#6c757d",
                  color: "white",
                  border: "none",
                  borderRadius: "8px",
                  fontWeight: "bold",
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                style={{
                  flex: 1,
                  padding: "14px",
                  background: loading ? "#7b68b5" : "#9370db",
                  color: "white",
                  border: "none",
                  borderRadius: "8px",
                  fontWeight: "bold",
                  boxShadow: loading
                    ? "none"
                    : "0 4px 20px rgba(147,112,219,0.5)",
                }}
              >
                {loading ? "Connecting..." : "Connect & Save"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default CredentialsPage;
