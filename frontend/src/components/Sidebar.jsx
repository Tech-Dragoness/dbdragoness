import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";

function Sidebar({
  dbType: initialDbType = "sql",
  handlerName: initialHandlerName = "",
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [dbType, setDbType] = useState(initialDbType);
  const [handlerName, setHandlerName] = useState(initialHandlerName);
  const [availableHandlers, setAvailableHandlers] = useState([]);
  const [switching, setSwitching] = useState(false);
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [needsCredentials, setNeedsCredentials] = useState(false);
  const [supportsCredentials, setSupportsCredentials] = useState(false); // ✅ NEW
  const [checkingCredentials, setCheckingCredentials] = useState(true);

  useEffect(() => {
    setDbType(initialDbType);
    setHandlerName(initialHandlerName);
  }, [initialDbType, initialHandlerName]);

  useEffect(() => {
    fetchCurrentState();
  }, []);

  const fetchCurrentState = async () => {
    try {
      const response = await axios.get("/api/current_state");
      if (response.data.success) {
        setDbType(response.data.db_type);
        setHandlerName(response.data.handler);
        setAvailableHandlers(response.data.available_handlers || []);

        // Check credentials after getting state
        await checkCredentials(response.data.handler);
      }
    } catch (err) {
      console.error("Failed to fetch current state:", err);
    } finally {
      setCheckingCredentials(false);
    }
  };

  const checkCredentials = async (handler) => {
    try {
      const response = await axios.get("/api/check_credentials");
      console.log("✅ Credentials check response:", response.data);

      if (response.data.success) {
        const needsCreds = response.data.needs_credentials;

        // ✅ NEW: Check if handler actually supports credentials
        // If needs_credentials is false AND handler doesn't error, it supports credentials
        // We determine support by whether the handler has credential management capability
        const handlerSupportsCredentials =
          response.data.handler_supports_credentials !== false;

        setNeedsCredentials(needsCreds);
        setSupportsCredentials(handlerSupportsCredentials); // ✅ NEW
        setIsSignedIn(!needsCreds && handlerSupportsCredentials); // ✅ UPDATED

        // If credentials are needed and we're not already on credentials page
        if (
          needsCreds &&
          handlerSupportsCredentials &&
          !location.pathname.includes("/credentials")
        ) {
          console.log(`🔐 Credentials needed for ${handler}, redirecting...`);
          navigate(`/credentials/${handler}`);
        }
      }
    } catch (err) {
      console.error("Failed to check credentials:", err);
      setNeedsCredentials(false);
      setSupportsCredentials(false); // ✅ NEW
      setIsSignedIn(false); // ✅ UPDATED
    } finally {
      setCheckingCredentials(false);
    }
  };

  const handleSwitch = async () => {
    if (switching) return;

    setSwitching(true);
    const newType = dbType === "sql" ? "nosql" : "sql";

    try {
      const response = await axios.post("/api/switch_handler", {
        type: newType,
        handler: null,
      });

      if (response.data.success) {
        setDbType(response.data.db_type);
        setHandlerName(response.data.handler);

        // Check if new handler needs credentials
        await checkCredentials(response.data.handler);

        // Only reload if not redirecting to credentials
        if (!response.data.needs_credentials) {
          navigate("/");
          setTimeout(() => {
            window.location.reload();
          }, 100);
        }
      } else {
        console.error("Switch failed:", response.data.error);
        alert("Failed to switch: " + response.data.error);
      }
    } catch (err) {
      console.error("Switch error:", err);
      alert("Failed to switch database type");
    } finally {
      setSwitching(false);
    }
  };

  const handleHandlerChange = async (newHandler) => {
    if (switching) return;

    setSwitching(true);

    try {
      const response = await axios.post("/api/switch_handler", {
        type: dbType,
        handler: newHandler,
      });

      if (response.data.success) {
        setHandlerName(response.data.handler);

        // Check if new handler needs credentials
        await checkCredentials(response.data.handler);

        // Only reload if not redirecting to credentials
        if (!response.data.needs_credentials) {
          navigate("/");
          window.location.reload();
        }
      } else {
        console.error("Handler switch failed:", response.data.error);
        alert("Failed to switch handler: " + response.data.error);
      }
    } catch (err) {
      console.error("Handler switch error:", err);
      alert("Failed to switch handler");
    } finally {
      setSwitching(false);
    }
  };

  const handleSignOut = async () => {
    // Confirmation dialog
    const confirmed = window.confirm(
      `Are you sure you want to sign out from ${handlerName}?\n\n` +
        "This will:\n" +
        "• Remove your stored credentials\n" +
        "• Redirect you to the credentials page\n" +
        "• Require re-entering credentials on next use"
    );

    if (!confirmed) {
      return;
    }

    try {
      const response = await axios.post("/api/sign_out", {
        handler_name: handlerName,
      });

      if (response.data.success) {
        console.log("✅ Signed out successfully");

        // Update state
        setIsSignedIn(false);
        setNeedsCredentials(true);

        // Navigate to credentials page
        navigate(`/credentials/${handlerName}`);

        // Reload page to clear any cached data
        setTimeout(() => {
          window.location.reload();
        }, 100);
      } else {
        alert("Failed to sign out: " + response.data.error);
      }
    } catch (err) {
      console.error("Sign out error:", err);
      alert(
        "Failed to sign out: " + (err.response?.data?.error || err.message)
      );
    }
  };

  return (
    <div className="sidebar">
      <h2>DBDragoness ({dbType.toUpperCase()})</h2>
      <p style={{ fontSize: "0.9em", color: "#f0f0f0", marginBottom: "10px" }}>
        {handlerName || "No Handler"}
      </p>

      {/* Handler Selector */}
      {availableHandlers.length > 1 && (
        <div style={{ marginBottom: "15px" }}>
          <select
            value={handlerName}
            onChange={(e) => handleHandlerChange(e.target.value)}
            disabled={switching}
            style={{
              width: "100%",
              padding: "8px",
              background: "rgba(30, 0, 51, 0.9)",
              color: "#f0f0f0",
              border: "1px solid #9370db",
              borderRadius: "5px",
              fontSize: "0.9em",
            }}
          >
            {availableHandlers.map((handler) => (
              <option key={handler} value={handler}>
                {handler}
              </option>
            ))}
          </select>
        </div>
      )}

      <a href="/react/">🏠 Home</a>

      <a
        href="#"
        onClick={(e) => {
          e.preventDefault();
          navigate("/query");
        }}
      >
        🔍 Query
      </a>
      <a
        href="#"
        onClick={(e) => {
          e.preventDefault();
          handleSwitch();
        }}
        style={{
          opacity: switching ? 0.5 : 1,
          cursor: switching ? "wait" : "pointer",
        }}
      >
        🔄{" "}
        {switching
          ? "Switching..."
          : `Switch to ${dbType === "sql" ? "NoSQL" : "SQL"}`}
      </a>

      {/* ✅ FIXED: Only show sign out if handler SUPPORTS credentials AND user is signed in */}
      {!checkingCredentials &&
        supportsCredentials &&
        isSignedIn &&
        !needsCredentials && (
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              handleSignOut();
            }}
            style={{
              marginTop: "20px",
              borderTop: "1px solid rgba(147, 112, 219, 0.3)",
              paddingTop: "15px",
              color: "#ff6b6b",
            }}
          >
            🚪 Sign Out
          </a>
        )}

    </div>
  );
}

export default Sidebar;
