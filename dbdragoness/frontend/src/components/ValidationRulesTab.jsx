import React, { useState, useEffect } from "react";
import axios from "axios";

function ValidationRulesTab({
  dbName,
  collectionName,
  keys,
  onSuccess,
  onError,
}) {
  const [validationRules, setValidationRules] = useState({});
  const [existingRules, setExistingRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fetchingRules, setFetchingRules] = useState(true);
  const [enumText, setEnumText] = useState({});

  useEffect(() => {
    fetchExistingRules();
  }, [dbName, collectionName]);

  const fetchExistingRules = async () => {
    try {
      setFetchingRules(true);
      const response = await axios.get(
        `/api/collection/${dbName}/${collectionName}/validation_rules`
      );

      console.log("📥 Fetched validation rules from backend:", response.data);

      if (response.data.success) {
        setExistingRules(response.data.rules || []);

        // Convert existing rules to form state
        const rulesObj = {};
        const enumTextObj = {};

        (response.data.rules || []).forEach((rule) => {
          console.log(`  Parsing rule for ${rule.column}:`, rule.expression);
          const parsed = parseValidationExpression(rule.expression);
          console.log(`  Parsed result:`, parsed);
          rulesObj[rule.column] = parsed;

          if (parsed.enum) {
            enumTextObj[rule.column] = parsed.enum.join(", ");
          }
        });

        console.log("📋 Final rulesObj to set:", rulesObj);
        setValidationRules(rulesObj);
        setEnumText(enumTextObj);
      }
    } catch (err) {
      console.error("Failed to fetch validation rules:", err);
    } finally {
      setFetchingRules(false);
    }
  };

  const parseValidationExpression = (expression) => {
    // Parse validation expression back to form fields
    const rules = {};

    if (expression.includes("type:")) {
      const typeMatch = expression.match(/type:\s*(\w+)/);
      if (typeMatch) {
        const rawType = typeMatch[1];

        const typeMap = {
          int: "number",
          double: "number",
          float: "number",
          decimal: "number",
          bool: "boolean",
          boolean: "boolean",
          string: "string",
          array: "array",
          object: "object",
          date: "date",
        };

        rules.type = typeMap[rawType] || "";
      }
    }

    if (expression.includes("required")) {
      rules.required = true;
    }

    if (expression.includes(">=")) {
      const minMatch = expression.match(/>=\s*([\d.]+)/);
      if (minMatch) rules.min = parseFloat(minMatch[1]);
    }

    if (expression.includes("<=")) {
      const maxMatch = expression.match(/<=\s*([\d.]+)/);
      if (maxMatch) rules.max = parseFloat(maxMatch[1]);
    }

    if (expression.includes("length >=")) {
      const minLenMatch = expression.match(/length\s*>=\s*(\d+)/);
      if (minLenMatch) rules.minLength = parseInt(minLenMatch[1]);
    }

    if (expression.includes("length <=")) {
      const maxLenMatch = expression.match(/length\s*<=\s*(\d+)/);
      if (maxLenMatch) rules.maxLength = parseInt(maxLenMatch[1]);
    }

    if (expression.includes("pattern:")) {
      const patternMatch = expression.match(/pattern:\s*(.+?)(?:,|$)/);
      if (patternMatch) rules.pattern = patternMatch[1].trim();
    }

    if (expression.includes("in [")) {
      const enumMatch = expression.match(/in\s*\[([^\]]+)\]/);
      if (enumMatch) {
        rules.enum = enumMatch[1]
          .split(",")
          .map((v) => v.trim().replace(/['"]/g, ""));
      }
    }

    return rules;
  };

  const updateFieldRule = (fieldName, ruleType, value) => {
    console.log(`🔧 updateFieldRule called:`, { fieldName, ruleType, value });
    
    setValidationRules((prev) => {
      const currentRules = prev[fieldName] || {};
      const newRules = { ...currentRules };

      console.log(`  Current rules for ${fieldName}:`, currentRules);

      // Update the specific rule
      if (value === null || value === undefined || value === "" || value === false) {
        // Remove the rule if value is empty/null/false
        console.log(`  ❌ Removing ${ruleType} (value is empty/null/false)`);
        delete newRules[ruleType];
      } else {
        // Set the rule
        console.log(`  ✅ Setting ${ruleType} =`, value);
        newRules[ruleType] = value;
      }

      // Special handling: When type changes, clean up type-specific validations
      if (ruleType === "type") {
        if (value !== "number") {
          // Removing number type - clean up numeric validations
          delete newRules.min;
          delete newRules.max;
        }
        if (value !== "string") {
          // Removing string type - clean up string validations
          delete newRules.minLength;
          delete newRules.maxLength;
          delete newRules.pattern;
        }
      }

      console.log(`  New rules for ${fieldName}:`, newRules);

      // If no rules remain for this field, remove the field entirely
      if (Object.keys(newRules).length === 0) {
        console.log(`  🗑️ No rules remain, removing field ${fieldName}`);
        const updatedRules = { ...prev };
        delete updatedRules[fieldName];
        console.log(`  Final validation rules:`, updatedRules);
        return updatedRules;
      }

      const result = {
        ...prev,
        [fieldName]: newRules,
      };
      console.log(`  Final validation rules:`, result);
      return result;
    });
  };

  const removeFieldRule = (fieldName) => {
    setValidationRules((prev) => {
      const newRules = { ...prev };
      delete newRules[fieldName];
      return newRules;
    });
    
    // Also clean up enum text
    setEnumText((prev) => {
      const newEnumText = { ...prev };
      delete newEnumText[fieldName];
      return newEnumText;
    });
  };

  const handleApplyRules = async () => {
    setLoading(true);

    // Debug: Log what we're sending
    console.log("🔍 Validation rules being sent:", JSON.stringify(validationRules, null, 2));

    try {
      const response = await axios.post(
        `/api/collection/${dbName}/${collectionName}/validation`,
        { validation_rules: validationRules }
      );

      if (response.data.success) {
        onSuccess();
        fetchExistingRules();
      } else {
        onError(response.data.error || "Failed to apply validation rules");
      }
    } catch (err) {
      onError(
        "Failed to apply validation: " +
          (err.response?.data?.error || err.message)
      );
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveAllRules = async () => {
    if (!window.confirm("Remove all validation rules from this collection?"))
      return;

    setLoading(true);

    try {
      const response = await axios.post(
        `/api/collection/${dbName}/${collectionName}/validation`,
        { validation_rules: {} }
      );

      if (response.data.success) {
        setValidationRules({});
        onSuccess();
        fetchExistingRules();
      } else {
        onError(response.data.error || "Failed to remove validation rules");
      }
    } catch (err) {
      onError(
        "Failed to remove validation: " +
          (err.response?.data?.error || err.message)
      );
    } finally {
      setLoading(false);
    }
  };

  if (fetchingRules) {
    return (
      <div style={{ textAlign: "center", padding: "40px", color: "#f0f0f0" }}>
        Loading validation rules...
      </div>
    );
  }

  return (
    <div style={{ color: "#f0f0f0" }}>
      <h3>Validation Rules</h3>
      <p style={{ color: "#ccc", fontSize: "0.9em", marginBottom: "20px" }}>
        Define validation rules for each field.
      </p>

      {existingRules.length > 0 && (
        <div
          style={{
            background: "rgba(76, 175, 80, 0.15)",
            padding: "15px",
            borderRadius: "8px",
            marginBottom: "20px",
            borderLeft: "4px solid #4caf50",
          }}
        >
          <strong>✓ Active Validation Rules:</strong>
          <ul style={{ margin: "10px 0 0 20px" }}>
            {existingRules.map((rule, idx) => (
              <li key={idx} style={{ margin: "5px 0" }}>
                <strong>{rule.column}:</strong> {rule.expression}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Field Selection */}
      <div style={{ marginBottom: "30px" }}>
        <h4>Add Validation for Fields:</h4>
        {keys
          .filter((k) => k !== "_id")
          .map((fieldName) => (
            <details
              key={fieldName}
              style={{
                background: "rgba(147, 112, 219, 0.1)",
                padding: "15px",
                borderRadius: "8px",
                marginBottom: "15px",
                border: validationRules[fieldName]
                  ? "2px solid #9370db"
                  : "1px solid #666",
              }}
            >
              <summary
                style={{
                  cursor: "pointer",
                  fontWeight: "bold",
                  fontSize: "1.1em",
                  color: validationRules[fieldName] ? "#bb86fc" : "#f0f0f0",
                }}
              >
                {fieldName} {validationRules[fieldName] && "✓"}
              </summary>

              <div style={{ marginTop: "15px" }}>
                {/* Data Type */}
                <div style={{ marginBottom: "15px" }}>
                  <label
                    style={{
                      display: "block",
                      marginBottom: "5px",
                      color: "#ccc",
                    }}
                  >
                    Data Type:
                  </label>
                  <select
                    value={validationRules[fieldName]?.type || ""}
                    onChange={(e) =>
                      updateFieldRule(fieldName, "type", e.target.value || null)
                    }
                    style={{
                      padding: "10px",
                      borderRadius: "5px",
                      border: "1px solid #9370db",
                      background: "rgba(147, 112, 219, 0.15)",
                      color: "#f0f0f0",
                      width: "100%",
                    }}
                  >
                    <option value="">No type constraint</option>
                    <option value="string">String</option>
                    <option value="number">Number</option>
                    <option value="boolean">Boolean</option>
                    <option value="array">Array</option>
                    <option value="object">Object</option>
                    <option value="date">Date</option>
                  </select>
                </div>

                {/* Required */}
                <div style={{ marginBottom: "15px" }}>
                  <label
                    style={{
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={validationRules[fieldName]?.required || false}
                      onChange={(e) =>
                        updateFieldRule(fieldName, "required", e.target.checked ? true : null)
                      }
                    />
                    <span>
                      Required field (must be present in all documents)
                    </span>
                  </label>
                </div>

                {/* Numeric Range (if number type) */}
                {validationRules[fieldName]?.type === "number" && (
                  <>
                    <div style={{ marginBottom: "15px" }}>
                      <label
                        style={{
                          display: "block",
                          marginBottom: "5px",
                          color: "#ccc",
                        }}
                      >
                        Minimum value:
                      </label>
                      <input
                        type="number"
                        step="any"
                        value={validationRules[fieldName]?.min ?? ''}
                        onWheel={(e) => e.target.blur()}
                        onChange={(e) =>
                          updateFieldRule(
                            fieldName,
                            "min",
                            e.target.value ? parseFloat(e.target.value) : null
                          )
                        }
                        placeholder="e.g. 0"
                        style={{
                          padding: "10px",
                          borderRadius: "5px",
                          border: "1px solid #9370db",
                          background: "rgba(147, 112, 219, 0.15)",
                          color: "#f0f0f0",
                          width: "100%",
                        }}
                      />
                    </div>
                    <div style={{ marginBottom: "15px" }}>
                      <label
                        style={{
                          display: "block",
                          marginBottom: "5px",
                          color: "#ccc",
                        }}
                      >
                        Maximum value:
                      </label>
                      <input
                        type="number"
                        step="any"
                        value={validationRules[fieldName]?.max ?? ''}
                        onWheel={(e) => e.target.blur()}
                        onChange={(e) =>
                          updateFieldRule(
                            fieldName,
                            "max",
                            e.target.value ? parseFloat(e.target.value) : null
                          )
                        }
                        placeholder="e.g. 100"
                        style={{
                          padding: "10px",
                          borderRadius: "5px",
                          border: "1px solid #9370db",
                          background: "rgba(147, 112, 219, 0.15)",
                          color: "#f0f0f0",
                          width: "100%",
                        }}
                      />
                    </div>
                  </>
                )}

                {/* String Length (if string type) */}
                {validationRules[fieldName]?.type === "string" && (
                  <>
                    <div style={{ marginBottom: "15px" }}>
                      <label
                        style={{
                          display: "block",
                          marginBottom: "5px",
                          color: "#ccc",
                        }}
                      >
                        Minimum length:
                      </label>
                      <input
                        type="number"
                        value={validationRules[fieldName]?.minLength || ""}
                        onWheel={(e) => e.target.blur()}
                        onChange={(e) =>
                          updateFieldRule(
                            fieldName,
                            "minLength",
                            e.target.value ? parseInt(e.target.value) : null
                          )
                        }
                        placeholder="e.g. 3"
                        style={{
                          padding: "10px",
                          borderRadius: "5px",
                          border: "1px solid #9370db",
                          background: "rgba(147, 112, 219, 0.15)",
                          color: "#f0f0f0",
                          width: "100%",
                        }}
                      />
                    </div>
                    <div style={{ marginBottom: "15px" }}>
                      <label
                        style={{
                          display: "block",
                          marginBottom: "5px",
                          color: "#ccc",
                        }}
                      >
                        Maximum length:
                      </label>
                      <input
                        type="number"
                        value={validationRules[fieldName]?.maxLength || ""}
                        onWheel={(e) => e.target.blur()}
                        onChange={(e) =>
                          updateFieldRule(
                            fieldName,
                            "maxLength",
                            e.target.value ? parseInt(e.target.value) : null
                          )
                        }
                        placeholder="e.g. 50"
                        style={{
                          padding: "10px",
                          borderRadius: "5px",
                          border: "1px solid #9370db",
                          background: "rgba(147, 112, 219, 0.15)",
                          color: "#f0f0f0",
                          width: "100%",
                        }}
                      />
                    </div>
                    <div style={{ marginBottom: "15px" }}>
                      <label
                        style={{
                          display: "block",
                          marginBottom: "5px",
                          color: "#ccc",
                        }}
                      >
                        Pattern (regex):
                      </label>
                      <input
                        type="text"
                        value={validationRules[fieldName]?.pattern || ""}
                        onChange={(e) =>
                          updateFieldRule(fieldName, "pattern", e.target.value)
                        }
                        placeholder="e.g. ^[A-Z].*"
                        style={{
                          padding: "10px",
                          borderRadius: "5px",
                          border: "1px solid #9370db",
                          background: "rgba(147, 112, 219, 0.15)",
                          color: "#f0f0f0",
                          width: "100%",
                          fontFamily: "monospace",
                        }}
                      />
                    </div>
                  </>
                )}

                {/* Enum (allowed values) */}
                <div style={{ marginBottom: "15px" }}>
                  <label
                    style={{
                      display: "block",
                      marginBottom: "5px",
                      color: "#ccc",
                    }}
                  >
                    Allowed values (comma-separated):
                  </label>
                  <input
                    type="text"
                    value={enumText[fieldName] || ""}
                    onChange={(e) => {
                      const raw = e.target.value;

                      // 1️⃣ always allow typing
                      setEnumText((prev) => ({
                        ...prev,
                        [fieldName]: raw,
                      }));

                      // 2️⃣ parse safely (non-destructive)
                      const values = raw
                        .split(",")
                        .map((v) => v.trim())
                        .filter((v) => v.length > 0);

                      // 3️⃣ store parsed enum where backend expects it
                      updateFieldRule(
                        fieldName,
                        "enum",
                        values.length ? values : null
                      );
                    }}
                    placeholder="e.g. active, pending, completed"
                    style={{
                      padding: "10px",
                      borderRadius: "5px",
                      border: "1px solid #9370db",
                      background: "rgba(147, 112, 219, 0.15)",
                      color: "#f0f0f0",
                      width: "100%",
                    }}
                  />
                </div>

                {/* Remove button */}
                {validationRules[fieldName] && (
                  <button
                    onClick={() => removeFieldRule(fieldName)}
                    style={{
                      padding: "8px 16px",
                      background: "#dc3545",
                      color: "white",
                      border: "none",
                      borderRadius: "5px",
                      cursor: "pointer",
                      fontWeight: "bold",
                    }}
                  >
                    Remove Validation for {fieldName}
                  </button>
                )}
              </div>
            </details>
          ))}
      </div>

      {/* Action Buttons */}
      <div style={{ display: "flex", gap: "15px", marginTop: "30px" }}>
        <button
          onClick={handleApplyRules}
          disabled={loading || Object.keys(validationRules).length === 0}
          style={{
            padding: "14px 28px",
            background: loading ? "#7b68b5" : "#9370db",
            color: "white",
            border: "none",
            borderRadius: "8px",
            cursor:
              loading || Object.keys(validationRules).length === 0
                ? "not-allowed"
                : "pointer",
            fontWeight: "bold",
            opacity:
              loading || Object.keys(validationRules).length === 0 ? 0.6 : 1,
          }}
        >
          {loading ? "Applying..." : "Apply Validation Rules"}
        </button>

        {existingRules.length > 0 && (
          <button
            onClick={handleRemoveAllRules}
            disabled={loading}
            style={{
              padding: "14px 28px",
              background: "#dc3545",
              color: "white",
              border: "none",
              borderRadius: "8px",
              cursor: loading ? "not-allowed" : "pointer",
              fontWeight: "bold",
              opacity: loading ? 0.6 : 1,
            }}
          >
            Remove All Rules
          </button>
        )}
      </div>

      {/* Info Box */}
      <div
        style={{
          background: "rgba(33, 150, 243, 0.15)",
          padding: "16px",
          borderRadius: "10px",
          borderLeft: "4px solid #2196f3",
          color: "#bbdefb",
          marginTop: "30px",
          fontSize: "0.95em",
        }}
      >
        <strong>💡 Note:</strong> Validation rules are enforced on all
        insert and update operations. Existing documents that violate new rules
        will remain but cannot be updated without fixing the violations.
      </div>
    </div>
  );
}

export default ValidationRulesTab;