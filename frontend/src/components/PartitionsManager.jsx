import React, { useState, useEffect } from "react";
import axios from "axios";

function PartitionsManager({ dbName, tables }) {
  const [selectedTable, setSelectedTable] = useState("");
  const [partitions, setPartitions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [supportsPartitions, setSupportsPartitions] = useState(false);
  const [partitionCaps, setPartitionCaps] = useState({
    list: false,
    create: false,
    delete: false,
  });

  // Partition config state
  const [partitionType, setPartitionType] = useState("RANGE");
  const [partitionColumn, setPartitionColumn] = useState("");
  const [partitionDefinitions, setPartitionDefinitions] = useState([
    { name: "", value: "" },
  ]);

  useEffect(() => {
    checkPartitionsSupport();
  }, [dbName]);

  useEffect(() => {
    if (selectedTable && supportsPartitions) {
      fetchPartitions(selectedTable);
      fetchPartitionCapabilities();
    }
  }, [selectedTable, supportsPartitions]);

  const checkPartitionsSupport = async () => {
    try {
      const response = await axios.get(`/api/db/${dbName}/partitions/support`);
      if (response.data.success) {
        setSupportsPartitions(response.data.supports_partitions || false);
      }
    } catch (err) {
      console.error("Failed to check partitions support:", err);
      setSupportsPartitions(false);
    }
  };

  const fetchPartitions = async (tableName) => {
    if (!tableName) return;

    try {
      setLoading(true);
      const response = await axios.get(
        `/api/db/${dbName}/table/${tableName}/partitions`
      );

      if (response.data.success) {
        setPartitions(response.data.partitions || []);
      } else {
        setError(response.data.error || "Failed to fetch partitions");
      }
    } catch (err) {
      console.error("Failed to fetch partitions:", err);
      setError("Failed to load partitions");
    } finally {
      setLoading(false);
    }
  };

  const fetchPartitionCapabilities = async () => {
    try {
      const res = await axios.get(`/api/db/${dbName}/partitions/capabilities`);

      if (res.data.success) {
        setPartitionCaps(res.data.capabilities);
      }
    } catch (err) {
      console.error("Failed to fetch partition capabilities", err);
    }
  };

  const handleCreatePartition = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    if (!selectedTable || !partitionColumn) {
      setError("Table and partition column are required");
      return;
    }

    const config = {
      type: partitionType,
      column: partitionColumn,
      definitions: partitionDefinitions.filter((d) => d.name && d.value),
    };

    // HASH partitions don't require definitions (optional for naming)
    if (partitionType !== "HASH" && config.definitions.length === 0) {
      setError(
        "At least one partition definition is required for RANGE and LIST partitions"
      );
      return;
    }

    try {
      const response = await axios.post(
        `/api/db/${dbName}/table/${selectedTable}/partitions/create`,
        { partition_config: config }
      );

      if (response.data.success) {
        setMessage(response.data.message);
        setShowCreateModal(false);
        setPartitionColumn("");
        setPartitionDefinitions([{ name: "", value: "" }]);
        fetchPartitions(selectedTable);
      } else {
        setError(response.data.error || "Failed to create partition");
      }
    } catch (err) {
      setError(
        "Failed to create partition: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  const handleDeletePartition = async (partitionName) => {
    if (
      !window.confirm(
        `Are you sure you want to delete partition ${partitionName}?`
      )
    ) {
      return;
    }

    try {
      const response = await axios.post(
        `/api/db/${dbName}/table/${selectedTable}/partitions/delete`,
        { partition_name: partitionName }
      );

      if (response.data.success) {
        setMessage(response.data.message);
        fetchPartitions(selectedTable);
      } else {
        setError(response.data.error || "Failed to delete partition");
      }
    } catch (err) {
      setError(
        "Failed to delete partition: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  const addPartitionDefinition = () => {
    setPartitionDefinitions([...partitionDefinitions, { name: "", value: "" }]);
  };

  const removePartitionDefinition = (index) => {
    setPartitionDefinitions(partitionDefinitions.filter((_, i) => i !== index));
  };

  const updatePartitionDefinition = (index, field, value) => {
    const updated = [...partitionDefinitions];
    updated[index][field] = value;
    setPartitionDefinitions(updated);
  };

  if (!supportsPartitions) {
    return (
      <div style={{ padding: "20px", color: "#f0f0f0" }}>
        <p style={{ textAlign: "center", fontStyle: "italic", color: "#666" }}>
          Partitions are not supported by this database handler.
        </p>
      </div>
    );
  }

  return (
    <div style={{ padding: "20px" }}>
      <h3 style={{ color: "#f0f0f0", marginBottom: "20px" }}>
        Table Partitions
      </h3>

      <div style={{ marginBottom: "20px" }}>
        <label
          style={{ display: "block", color: "#f0f0f0", marginBottom: "5px" }}
        >
          Select Table:
        </label>
        <select
          value={selectedTable}
          onChange={(e) => setSelectedTable(e.target.value)}
          style={{
            padding: "10px",
            width: "300px",
            border: "1.5px solid #9370db",
            borderRadius: "5px",
            background: "rgba(30, 0, 51, 0.5)",
            color: "#f0f0f0",
            fontSize: "14px",
          }}
        >
          <option value="">-- Select a table --</option>
          {tables.map((table) => {
            const tableName = typeof table === "string" ? table : table.name;
            return (
              <option key={tableName} value={tableName}>
                {tableName}
              </option>
            );
          })}
        </select>
      </div>

      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}

      {selectedTable && (
        <>
          {partitionCaps.create ? (
            <button
              onClick={() => setShowCreateModal(true)}
              style={{
                padding: "10px 20px",
                background: "#9370db",
                color: "white",
                border: "none",
                borderRadius: "5px",
                cursor: "pointer",
                marginBottom: "20px",
              }}
            >
              Create Partition
            </button>
          ) : (
            <div
              style={{
                marginBottom: "20px",
                padding: "10px 14px",
                background: "rgba(255, 193, 7, 0.15)",
                borderLeft: "4px solid #ffc107",
                borderRadius: "6px",
                color: "#ffecb5",
                fontSize: "0.9em",
              }}
            >
              ⚠️ This database does not support creating partitions after table
              creation.
            </div>
          )}

          {loading ? (
            <div className="loading">Loading partitions...</div>
          ) : partitions.length > 0 ? (
            <table className="table-list">
              <thead>
                <tr>
                  <th>Partition Name</th>
                  <th>Type</th>
                  <th>Expression</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {partitions.map((partition) => (
                  <tr key={partition.name}>
                    <td>
                      <strong>{partition.name}</strong>
                    </td>
                    <td>{partition.type || "N/A"}</td>
                    <td>{partition.expression || "N/A"}</td>
                    <td>
                      {partitionCaps.delete && (
                        <button
                          onClick={() => handleDeletePartition(partition.name)}
                          style={{ background: "#dc3545" }}
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p
              style={{
                textAlign: "center",
                fontStyle: "italic",
                color: "#666",
              }}
            >
              No partitions found for this table.
            </p>
          )}
        </>
      )}

      {showCreateModal && partitionCaps.create && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.7)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "#2a2a2a",
              padding: "30px",
              borderRadius: "10px",
              width: "90%",
              maxWidth: "600px",
              maxHeight: "80vh",
              overflowY: "auto",
            }}
          >
            <h3 style={{ color: "#f0f0f0", marginTop: 0 }}>
              Create Partition for {selectedTable}
            </h3>

            <form onSubmit={handleCreatePartition}>
              <div style={{ marginBottom: "20px" }}>
                <label
                  style={{
                    display: "block",
                    color: "#f0f0f0",
                    marginBottom: "5px",
                  }}
                >
                  Partition Type:
                </label>
                <select
                  value={partitionType}
                  onChange={(e) => setPartitionType(e.target.value)}
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
                  <option value="RANGE">RANGE</option>
                  <option value="LIST">LIST</option>
                  <option value="HASH">HASH</option>
                </select>
              </div>

              <div style={{ marginBottom: "20px" }}>
                <label
                  style={{
                    display: "block",
                    color: "#f0f0f0",
                    marginBottom: "5px",
                  }}
                >
                  Partition Column:
                </label>
                <input
                  type="text"
                  value={partitionColumn}
                  onChange={(e) => setPartitionColumn(e.target.value)}
                  placeholder="e.g., created_date, id, category"
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

              <div style={{ marginBottom: "20px" }}>
                <label
                  style={{
                    display: "block",
                    color: "#f0f0f0",
                    marginBottom: "10px",
                  }}
                >
                  Partition Definitions:
                </label>
                {partitionDefinitions.map((def, index) => (
                  <div
                    key={index}
                    style={{
                      display: "flex",
                      gap: "10px",
                      marginBottom: "10px",
                    }}
                  >
                    <input
                      type="text"
                      value={def.name}
                      onChange={(e) =>
                        updatePartitionDefinition(index, "name", e.target.value)
                      }
                      placeholder="Partition name"
                      style={{
                        flex: 1,
                        padding: "10px",
                        border: "1.5px solid #9370db",
                        borderRadius: "5px",
                        background: "rgba(30, 0, 51, 0.5)",
                        color: "#f0f0f0",
                        fontSize: "14px",
                      }}
                    />
                    <input
                      type="text"
                      value={def.value}
                      onChange={(e) =>
                        updatePartitionDefinition(
                          index,
                          "value",
                          e.target.value
                        )
                      }
                      placeholder={
                        partitionType === "RANGE"
                          ? "For dates: 2023, 2024, etc. For numbers: 100, 1000, MAXVALUE"
                          : partitionType === "LIST"
                          ? "For MySQL: Use numbers (1, 2, 3). Strings not supported!"
                          : "(Optional - auto-numbered if empty)"
                      }
                      style={{
                        flex: 2,
                        padding: "10px",
                        border: "1.5px solid #9370db",
                        borderRadius: "5px",
                        background: "rgba(30, 0, 51, 0.5)",
                        color: "#f0f0f0",
                        fontSize: "14px",
                      }}
                    />
                    {partitionDefinitions.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removePartitionDefinition(index)}
                        style={{
                          padding: "10px",
                          background: "#dc3545",
                          color: "white",
                          border: "none",
                          borderRadius: "5px",
                          cursor: "pointer",
                        }}
                      >
                        ✕
                      </button>
                    )}
                  </div>
                ))}
                <button
                  type="button"
                  onClick={addPartitionDefinition}
                  style={{
                    padding: "8px 16px",
                    background: "#28a745",
                    color: "white",
                    border: "none",
                    borderRadius: "5px",
                    cursor: "pointer",
                    fontSize: "14px",
                  }}
                >
                  + Add Partition
                </button>
              </div>

              <div
                style={{
                  display: "flex",
                  gap: "10px",
                  justifyContent: "flex-end",
                }}
              >
                <button
                  type="button"
                  onClick={() => {
                    setShowCreateModal(false);
                    setPartitionColumn("");
                    setPartitionDefinitions([{ name: "", value: "" }]);
                  }}
                  style={{
                    padding: "10px 20px",
                    background: "#6c757d",
                    color: "white",
                    border: "none",
                    borderRadius: "5px",
                    cursor: "pointer",
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{
                    padding: "10px 20px",
                    background: "#9370db",
                    color: "white",
                    border: "none",
                    borderRadius: "5px",
                    cursor: "pointer",
                  }}
                >
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default PartitionsManager;
