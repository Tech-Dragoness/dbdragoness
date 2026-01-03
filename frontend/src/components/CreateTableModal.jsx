import React, { useState, useEffect } from "react";
import axios from "axios";

function CreateTableModal({ dbName, onClose, onSuccess }) {
  const [step, setStep] = useState(1);
  const [tableName, setTableName] = useState("");
  const [numColumns, setNumColumns] = useState("");
  const [columns, setColumns] = useState([]);
  const [checkConstraints, setCheckConstraints] = useState({});
  const [showCheckEditors, setShowCheckEditors] = useState({});
  const [types, setTypes] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [supportsNonPkAutoincrement, setSupportsNonPkAutoincrement] =
    useState(true);
  const [handlerName, setHandlerName] = useState("");

  useEffect(() => {
    fetchSupportedTypes();
  }, []);

  const fetchSupportedTypes = async () => {
    try {
      const response = await axios.get(`/api/db/${dbName}/supported_types`);
      if (response.data.success) {
        setTypes(response.data.types || ["TEXT", "INTEGER", "REAL", "BLOB"]);
      }
    } catch (err) {
      console.error("Failed to fetch types:", err);
      setTypes(["TEXT", "INTEGER", "REAL", "BLOB"]);
    }

    // Fetch capabilities
    try {
      const capResponse = await axios.get(`/api/db/${dbName}/capabilities`);
      if (capResponse.data.success) {
        setSupportsNonPkAutoincrement(
          capResponse.data.capabilities.supports_non_pk_autoincrement
        );
      }
    } catch (err) {
      console.error("Failed to fetch capabilities:", err);
      setSupportsNonPkAutoincrement(true);
    }

    // Fetch current handler name
    try {
      const stateResponse = await axios.get(`/api/current_state`);
      if (stateResponse.data.success) {
        setHandlerName(stateResponse.data.handler);
      }
    } catch (err) {
      console.error("Failed to fetch handler name:", err);
    }
  };

  const canSupportAutoincrement = (type, handlerName) => {
    if (handlerName === "PostgreSQL") {
      const autoincrementTypes = [
        "SERIAL",
        "BIGSERIAL",
        "SMALLSERIAL",
        "INTEGER",
        "BIGINT",
        "SMALLINT",
      ];
      return autoincrementTypes.includes(type?.toUpperCase());
    } else if (handlerName === "MySQL") {
      const autoincrementTypes = [
        "INT",
        "INTEGER",
        "BIGINT",
        "SMALLINT",
        "TINYINT",
        "MEDIUMINT",
      ];
      return autoincrementTypes.includes(type?.toUpperCase());
    } else {
      const autoincrementTypes = [
        "INTEGER",
        "INT",
        "BIGINT",
        "SMALLINT",
        "TINYINT",
      ];
      return autoincrementTypes.includes(type?.toUpperCase());
    }
  };

  const handleStep1Submit = (e) => {
    e.preventDefault();
    setError("");

    if (!tableName.match(/^[a-zA-Z][a-zA-Z0-9_]*$/)) {
      setError(
        "Table name must start with a letter, contain only letters, numbers, underscores."
      );
      return;
    }

    const num = parseInt(numColumns);
    if (isNaN(num) || num < 1 || num > 20) {
      setError(
        "Number of columns must be between 1 and 20. More can be added later!"
      );
      return;
    }

    // Initialize columns
    const initialColumns = [];
    for (let i = 0; i < num; i++) {
      initialColumns.push({
        name: "",
        type: types[0] || "TEXT",
        is_pk: false,
        is_not_null: false,
        is_autoincrement: false,
        is_unique: false,
      });
    }
    setColumns(initialColumns);
    setCheckConstraints({});
    setShowCheckEditors({});
    setStep(2);
  };

  const handleColumnChange = (index, field, value) => {
    const updated = [...columns];

    // Handle autoincrement ENABLE
    if (field === "is_autoincrement" && value === true) {
      updated.forEach((col, i) => {
        if (i === index) {
          col.is_autoincrement = true;
          col.is_unique = true;
          col.is_not_null = true;
        } else if (col.is_autoincrement) {
          col.is_autoincrement = false;
          col.is_unique = col.is_pk ? true : false;
          col.is_not_null = col.is_pk ? true : false;
        }
      });
      setColumns(updated);
      return;
    }

    // Handle autoincrement DISABLE
    if (field === "is_autoincrement" && value === false) {
      updated[index] = {
        ...updated[index],
        is_autoincrement: false,
        is_unique: updated[index].is_pk ? true : false,
        is_not_null: updated[index].is_pk ? true : false,
      };
      setColumns(updated);
      return;
    }

    // Prevent unchecking unique when autoincrement is active
    if (
      field === "is_unique" &&
      value === false &&
      updated[index].is_autoincrement
    ) {
      return;
    }

    // Prevent unchecking notnull when autoincrement is active
    if (
      field === "is_not_null" &&
      value === false &&
      updated[index].is_autoincrement
    ) {
      return;
    }

    // Default behavior for other fields
    updated[index] = { ...updated[index], [field]: value };
    setColumns(updated);
  };

  const handlePKChange = (index, checked) => {
    const updated = [...columns];

    if (checked) {
      updated.forEach((col, idx) => {
        if (idx !== index) {
          col.is_pk = false;
          col.is_not_null = false;
          col.is_unique = false;
        }
      });
      updated[index].is_pk = true;
      updated[index].is_not_null = true;
      updated[index].is_unique = true;
    } else {
      updated[index].is_pk = false;
      updated[index].is_not_null = false;
      updated[index].is_unique = false;
    }

    setColumns(updated);
  };

  const handleCreateTable = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    // Validate columns
    for (const col of columns) {
      if (!col.name || !col.type) {
        setError("All columns must have a name and type.");
        setLoading(false);
        return;
      }
    }

    try {
      // ✅ Add CHECK constraints to columns
      const columnsWithChecks = columns.map((col) => {
        const colData = { ...col };
        const checkExpr = checkConstraints[col.name];
        if (checkExpr && checkExpr.trim()) {
          colData.check_constraint = checkExpr.trim();
        }
        return colData;
      });

      const response = await axios.post(`/api/db/${dbName}/create_table`, {
        table_name: tableName,
        columns: columnsWithChecks,
      });

      if (response.data.success) {
        onSuccess(response.data.table_name);
        onClose();
      } else {
        setError(response.data.error || "Failed to create table");
      }
    } catch (err) {
      console.error("Create table error:", err);
      setError(
        "Failed to create table: " + (err.response?.data?.error || err.message)
      );
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
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "linear-gradient(135deg, #1e0033, #3a0066)",
          padding: "30px",
          borderRadius: "15px",
          maxWidth: "1100px",
          width: "95%",
          maxHeight: "85vh",
          overflowY: "auto",
          border: "2px solid #9370db",
          boxShadow: "0 10px 40px rgba(147, 112, 219, 0.6)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ color: "#f0f0f0", marginBottom: "20px" }}>
          Create Table in {dbName}
        </h2>

        {error && (
          <div className="error" style={{ marginBottom: "15px" }}>
            {error}
          </div>
        )}

        {step === 1 && (
          <div>
            <div style={{ marginBottom: "15px" }}>
              <label
                style={{
                  color: "#f0f0f0",
                  display: "block",
                  marginBottom: "5px",
                }}
              >
                Table Name:
              </label>
              <input
                type="text"
                value={tableName}
                onChange={(e) => setTableName(e.target.value)}
                placeholder="e.g., users, products"
                style={{
                  width: "100%",
                  padding: "10px",
                  border: "1.5px solid #9370db",
                  borderRadius: "5px",
                  background: "rgba(147, 112, 219, 0.1)",
                  color: "#f0f0f0",
                  fontSize: "14px",
                }}
              />
            </div>

            <div style={{ marginBottom: "20px" }}>
              <label
                style={{
                  color: "#f0f0f0",
                  display: "block",
                  marginBottom: "5px",
                }}
              >
                Number of Columns (1-20):
              </label>
              <input
                type="number"
                value={numColumns}
                onChange={(e) => setNumColumns(e.target.value)}
                min="1"
                max="20"
                style={{
                  width: "100%",
                  padding: "10px",
                  border: "1.5px solid #9370db",
                  borderRadius: "5px",
                  background: "rgba(147, 112, 219, 0.1)",
                  color: "#f0f0f0",
                  fontSize: "14px",
                }}
              />
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
                onClick={onClose}
                style={{ background: "#6c757d" }}
              >
                Cancel
              </button>
              <button
                onClick={handleStep1Submit}
                style={{ background: "#9370db" }}
              >
                Next
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <div style={{ marginBottom: "20px" }}>
              <h3 style={{ color: "#f0f0f0", marginBottom: "15px" }}>
                Define Columns for {tableName}
              </h3>

              {/* ✅ SCROLLABLE CONTAINER for columns */}
              <div
                style={{
                  marginBottom: "20px",
                  overflowX: "auto",
                  overflowY: "visible",
                  paddingBottom: "10px",
                  maxWidth: "100%",
                }}
              >
                <div
                  style={{
                    minWidth: "1200px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "10px",
                  }}
                >
                  {columns.map((col, idx) => (
                    <div key={idx}>
                      {/* Main column row */}
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns:
                            "200px 230px 120px 120px 120px 100px 100px",
                          gap: "8px",
                          alignItems: "center",
                          padding: "12px",
                          background: "rgba(147, 112, 219, 0.15)",
                          borderRadius: "8px",
                          width: "100%",
                          boxSizing: "border-box",
                        }}
                      >
                        {/* Column Name */}
                        <input
                          type="text"
                          value={col.name}
                          onChange={(e) =>
                            handleColumnChange(idx, "name", e.target.value)
                          }
                          placeholder={`Column ${idx + 1}`}
                          style={{
                            padding: "8px",
                            border: "1.5px solid #9370db",
                            borderRadius: "5px",
                            background: "rgba(30, 0, 51, 0.5)",
                            color: "#f0f0f0",
                          }}
                        />

                        {/* Type and Length Combined */}
                        <div
                          style={{
                            display: "flex",
                            gap: "5px",
                            alignItems: "center",
                            width: "100%",
                          }}
                        >
                          <select
                            value={
                              col.type.includes("(")
                                ? col.type.split("(")[0]
                                : col.type
                            }
                            onChange={(e) => {
                              const baseType = e.target.value;
                              const needsLength = [
                                "VARCHAR",
                                "CHAR",
                                "DECIMAL",
                                "NUMERIC",
                              ].includes(baseType);

                              if (needsLength) {
                                const currentLength = col.type.includes("(")
                                  ? col.type.match(/\((\d+)\)/)?.[1] || "255"
                                  : "255";
                                handleColumnChange(
                                  idx,
                                  "type",
                                  `${baseType}(${currentLength})`
                                );
                              } else {
                                handleColumnChange(idx, "type", baseType);
                              }
                            }}
                            style={{
                              padding: "8px",
                              border: "1.5px solid #9370db",
                              borderRadius: "5px",
                              background: "rgba(30, 0, 51, 0.9)",
                              color: "#f0f0f0",
                              flex: 1,
                              minWidth: "90px",
                            }}
                          >
                            {types.map((type) => (
                              <option key={type} value={type}>
                                {type}
                              </option>
                            ))}
                          </select>

                          {/* Length Input */}
                          {(() => {
                            const baseType = col.type.includes("(")
                              ? col.type.split("(")[0]
                              : col.type;
                            const needsLength = [
                              "VARCHAR",
                              "CHAR",
                              "DECIMAL",
                              "NUMERIC",
                            ].includes(baseType);

                            if (needsLength) {
                              const currentLength = col.type.includes("(")
                                ? col.type.match(/\((\d+)\)/)?.[1] || ""
                                : "";

                              return (
                                <input
                                  type="text"
                                  value={currentLength}
                                  onChange={(e) => {
                                    const length = e.target.value;
                                    if (length === "" || /^\d+$/.test(length)) {
                                      if (length === "") {
                                        handleColumnChange(
                                          idx,
                                          "type",
                                          baseType
                                        );
                                      } else {
                                        handleColumnChange(
                                          idx,
                                          "type",
                                          `${baseType}(${length})`
                                        );
                                      }
                                    }
                                  }}
                                  onBlur={(e) => {
                                    if (e.target.value === "") {
                                      handleColumnChange(
                                        idx,
                                        "type",
                                        `${baseType}(255)`
                                      );
                                    }
                                  }}
                                  placeholder="Len"
                                  style={{
                                    width: "70px",
                                    padding: "8px",
                                    border: "1.5px solid #9370db",
                                    borderRadius: "5px",
                                    background: "rgba(30, 0, 51, 0.5)",
                                    color: "#f0f0f0",
                                    textAlign: "center",
                                  }}
                                />
                              );
                            }

                            return null;
                          })()}
                        </div>

                        {/* Primary Key Checkbox */}
                        <label
                          style={{
                            color: "#f0f0f0",
                            display: "flex",
                            alignItems: "center",
                            cursor: "pointer",
                            fontSize: "0.9em",
                            whiteSpace: "nowrap",
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={col.is_pk}
                            onChange={(e) =>
                              handlePKChange(idx, e.target.checked)
                            }
                            style={{ marginRight: "5px" }}
                          />
                          Primary Key
                        </label>

                        {/* Not Null Checkbox */}
                        <label
                          style={{
                            color: "#f0f0f0",
                            display: "flex",
                            alignItems: "center",
                            cursor:
                              col.is_pk || col.is_autoincrement
                                ? "not-allowed"
                                : "pointer",
                            opacity:
                              col.is_pk || col.is_autoincrement ? 0.6 : 1,
                            fontSize: "0.9em",
                            whiteSpace: "nowrap",
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={
                              col.is_pk ||
                              col.is_not_null ||
                              col.is_autoincrement ||
                              false
                            }
                            onChange={(e) =>
                              handleColumnChange(
                                idx,
                                "is_not_null",
                                e.target.checked
                              )
                            }
                            disabled={col.is_pk || col.is_autoincrement}
                            style={{ marginRight: "5px" }}
                          />
                          Not Null
                        </label>

                        {/* Autoincrement Checkbox */}
                        <label
                          style={{
                            color: "#f0f0f0",
                            display: "flex",
                            alignItems: "center",
                            cursor:
                              (supportsNonPkAutoincrement || col.is_pk) &&
                              canSupportAutoincrement(col.type, handlerName)
                                ? "pointer"
                                : "not-allowed",
                            opacity:
                              (supportsNonPkAutoincrement || col.is_pk) &&
                              canSupportAutoincrement(col.type, handlerName)
                                ? 1
                                : 0.6,
                            fontSize: "0.9em",
                            whiteSpace: "nowrap",
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={col.is_autoincrement}
                            onChange={(e) => {
                              if (
                                canSupportAutoincrement(col.type, handlerName)
                              ) {
                                if (!supportsNonPkAutoincrement && !col.is_pk) {
                                  return;
                                }
                                handleColumnChange(
                                  idx,
                                  "is_autoincrement",
                                  e.target.checked
                                );
                              }
                            }}
                            disabled={
                              (!supportsNonPkAutoincrement && !col.is_pk) ||
                              !canSupportAutoincrement(col.type, handlerName)
                            }
                            style={{ marginRight: "5px" }}
                          />
                          Auto Inc
                        </label>

                        {/* Unique Checkbox */}
                        <label
                          style={{
                            color: "#f0f0f0",
                            display: "flex",
                            alignItems: "center",
                            cursor:
                              col.is_pk || col.is_autoincrement
                                ? "not-allowed"
                                : "pointer",
                            opacity:
                              col.is_pk || col.is_autoincrement ? 0.6 : 1,
                            fontSize: "0.9em",
                            whiteSpace: "nowrap",
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={
                              col.is_pk ||
                              col.is_unique ||
                              col.is_autoincrement ||
                              false
                            }
                            onChange={(e) => {
                              if (!col.is_pk && !col.is_autoincrement) {
                                handleColumnChange(
                                  idx,
                                  "is_unique",
                                  e.target.checked
                                );
                              }
                            }}
                            disabled={col.is_pk || col.is_autoincrement}
                            style={{ marginRight: "5px" }}
                          />
                          Unique
                        </label>

                        {/* ✅ CHECK Constraint Toggle */}
                        <label
                          style={{
                            color: "#f0f0f0",
                            display: "flex",
                            alignItems: "center",
                            cursor: "pointer",
                            fontSize: "0.9em",
                            whiteSpace: "nowrap",
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={Boolean(
                              checkConstraints[col.name] ||
                                showCheckEditors[col.name]
                            )}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setShowCheckEditors({
                                  ...showCheckEditors,
                                  [col.name]: true,
                                });
                                if (!checkConstraints[col.name]) {
                                  setCheckConstraints({
                                    ...checkConstraints,
                                    [col.name]: "",
                                  });
                                }
                              } else {
                                const newChecks = { ...checkConstraints };
                                delete newChecks[col.name];
                                setCheckConstraints(newChecks);

                                const newEditors = { ...showCheckEditors };
                                delete newEditors[col.name];
                                setShowCheckEditors(newEditors);
                              }
                            }}
                            style={{ marginRight: "5px" }}
                          />
                          CHECK
                        </label>
                      </div>

                      {/* ✅ CHECK Constraint Editor */}
                      {(checkConstraints[col.name] !== undefined ||
                        showCheckEditors[col.name]) && (
                        <div
                          style={{
                            marginTop: "5px",
                            marginLeft: "15px",
                            padding: "10px",
                            background: "rgba(76, 175, 80, 0.1)",
                            border: "1.5px solid #4caf50",
                            borderRadius: "5px",
                          }}
                        >
                          <div
                            style={{
                              marginBottom: "5px",
                              color: "#4caf50",
                              fontSize: "0.85em",
                              fontWeight: "bold",
                            }}
                          >
                            CHECK Constraint for {col.name}:
                          </div>
                          <input
                            type="text"
                            value={checkConstraints[col.name] || ""}
                            onChange={(e) => {
                              setCheckConstraints({
                                ...checkConstraints,
                                [col.name]: e.target.value,
                              });
                            }}
                            placeholder="e.g., age > 0, price BETWEEN 0 AND 1000"
                            style={{
                              width: "100%",
                              padding: "8px",
                              border: "1.5px solid #4caf50",
                              borderRadius: "5px",
                              background: "rgba(30, 0, 51, 0.5)",
                              color: "#f0f0f0",
                              fontFamily: "monospace",
                              fontSize: "0.9em",
                            }}
                          />
                          <div
                            style={{
                              marginTop: "5px",
                              fontSize: "0.75em",
                              color: "#ccc",
                            }}
                          >
                            💡 Examples: age {">"} 18, price {">"} 0, status IN
                            ('active', 'pending')
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
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
                onClick={() => setStep(1)}
                style={{ background: "#6c757d" }}
              >
                Back
              </button>
              <button
                type="button"
                onClick={onClose}
                style={{ background: "#6c757d" }}
              >
                Cancel
              </button>
              <button
                onClick={handleCreateTable}
                disabled={loading}
                style={{
                  background: loading ? "#ccc" : "#9370db",
                  cursor: loading ? "not-allowed" : "pointer",
                }}
              >
                {loading ? "Creating..." : "Create Table"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
export default CreateTableModal;
