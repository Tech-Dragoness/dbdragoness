import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import EditTriggerModal from "../components/EditTriggerModal";
import Sidebar from "../components/Sidebar";

function TriggersList() {
  const { dbName } = useParams();
  const navigate = useNavigate();

  const [triggers, setTriggers] = useState([]);
  const [supportsTriggers, setSupportsTriggers] = useState(false);
  const [dbType, setDbType] = useState("sql");
  const [handlerName, setHandlerName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingTrigger, setEditingTrigger] = useState(null);

  useEffect(() => {
    fetchTriggers();
  }, [dbName]);

  const fetchTriggers = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/api/db/${dbName}/triggers`);

      if (response.data.success) {
        setTriggers(response.data.triggers);
        setSupportsTriggers(response.data.supports_triggers);
        setDbType(response.data.db_type);
        setHandlerName(response.data.handler);
      } else {
        setError(response.data.error || "Failed to fetch triggers");
      }
    } catch (err) {
      console.error("Failed to fetch triggers:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleEditTrigger = (trigger) => {
    setEditingTrigger(trigger);
    setShowEditModal(true);
  };

  const handleDeleteTrigger = async (triggerName) => {
    if (
      !window.confirm(`Are you sure you want to delete trigger ${triggerName}?`)
    ) {
      return;
    }

    try {
      const response = await axios.post(`/api/db/${dbName}/triggers/delete`, {
        trigger_name: triggerName,
      });

      if (response.data.success) {
        setMessage(`Trigger ${triggerName} deleted successfully`);
        fetchTriggers();
      } else {
        setError(response.data.error || "Failed to delete trigger");
      }
    } catch (err) {
      setError(
        "Failed to delete trigger: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  if (loading) {
    return (
      <>
        <Sidebar dbType={dbType} handlerName={handlerName} />
        <div className="center">
          <div className="loading">Loading triggers...</div>
        </div>
      </>
    );
  }

  return (
    <>
      <Sidebar dbType={dbType} handlerName={handlerName} />
      <div className="center">
        <h2 style={{ color: "#f0f0f0" }}>All Triggers in {dbName}</h2>
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate(`/db/${dbName}`);
          }}
          style={{ color: "#bb86fc" }}
        >
          ← Back to Tables
        </a>

        {error && <div className="error">{error}</div>}
        {message && <div className="success">{message}</div>}

        {!supportsTriggers ? (
          <p style={{ color: "orange", marginTop: "20px" }}>
            Warning: This database does not support triggers.
          </p>
        ) : triggers.length > 0 ? (
          <div style={{ overflowX: "auto", width: "95%", margin: "20px auto" }}>
            <table
              className="result-table"
              style={{ width: "100%", minWidth: "800px" }}
            >
              <thead>
                <tr>
                  <th>Trigger Name</th>
                  <th>Table</th>
                  <th>Timing</th>
                  <th>Event</th>
                  <th style={{ minWidth: "300px" }}>SQL</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {triggers.map((trigger, idx) => (
                  <tr key={idx}>
                    <td>{trigger.name}</td>
                    <td>
                      <a
                        href="#"
                        onClick={(e) => {
                          e.preventDefault();
                          navigate(
                            `/db/${dbName}/table/${trigger.table}?tab=triggers`
                          );
                        }}
                        style={{ color: "#9370db" }}
                      >
                        {trigger.table}
                      </a>
                    </td>
                    <td>{trigger.timing || "N/A"}</td>
                    <td>{trigger.event || "N/A"}</td>
                    <td>
                      <pre
                        style={{
                          fontSize: "0.85em",
                          margin: 0,
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                          maxWidth: "400px",
                        }}
                      >
                        {trigger.sql}
                      </pre>
                    </td>
                    <td>
                      <button
                        onClick={() => handleEditTrigger(trigger)}
                        style={{
                          background: "#17a2b8",
                          color: "white",
                          border: "none",
                          padding: "5px 10px",
                          borderRadius: "4px",
                          cursor: "pointer",
                          marginRight: "5px",
                          whiteSpace: "nowrap",
                        }}
                      >
                        ✏️ Edit
                      </button>
                      <button
                        onClick={() => handleDeleteTrigger(trigger.name)}
                        style={{
                          background: "#dc3545",
                          color: "white",
                          border: "none",
                          padding: "5px 10px",
                          borderRadius: "4px",
                          cursor: "pointer",
                          whiteSpace: "nowrap",
                        }}
                      >
                        🗑️ Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div
            style={{
              textAlign: "center",
              padding: "40px",
              background: "#f8f8f8",
              borderRadius: "10px",
              margin: "20px auto",
              maxWidth: "600px",
            }}
          >
            <p style={{ fontSize: "3em", margin: 0 }}>🔍</p>
            <h3 style={{ color: "#666" }}>No Triggers Found</h3>
            <p style={{ color: "#999" }}>
              Create triggers using the Triggers tab in table views.
            </p>
          </div>
        )}
      </div>
      {showEditModal && editingTrigger && (
        <EditTriggerModal
          dbName={dbName}
          tableName={editingTrigger.table}
          triggerName={editingTrigger.name}
          onClose={() => {
            setShowEditModal(false);
            setEditingTrigger(null);
          }}
          onSuccess={(msg) => {
            setMessage(msg);
            fetchTriggers();
          }}
        />
      )}
    </>
  );
}

export default TriggersList;
