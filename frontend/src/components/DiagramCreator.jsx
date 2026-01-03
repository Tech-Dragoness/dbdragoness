import React, { useState, useEffect } from "react";
import mermaid from "mermaid";
import axios from "axios";

// Initialize Mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: "default",
  securityLevel: "loose",
});

function DiagramCreator({ dbName, dbType }) {
  const [diagramType, setDiagramType] = useState(
    dbType === "sql" ? "er" : "collections"
  );
  const [diagramData, setDiagramData] = useState(null);
  const [diagramCode, setDiagramCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [diagramSvg, setDiagramSvg] = useState("");
  const [relationships, setRelationships] = useState([]);
  const [showRelationshipsModal, setShowRelationshipsModal] = useState(false);
  const [showAddRelationshipForm, setShowAddRelationshipForm] = useState(false);
  const [newRelationship, setNewRelationship] = useState({
    from: "",
    to: "",
    cardinality: "||--o{", // default: one-to-many
    relationshipName: "", // new field for relationship description
  });
  const [editingRelationshipIndex, setEditingRelationshipIndex] =
    useState(null);

  useEffect(() => {
    if (!diagramData || !diagramData.tables) return;

    const mergedData = {
      ...diagramData,
      relationships: relationships || [],
    };

    generateMermaidCode(mergedData, diagramType);
  }, [diagramData, relationships, diagramType]);

  useEffect(() => {
    loadDiagramData();
  }, [diagramType]);

  const loadDiagramData = async () => {
    setLoading(true);
    setError("");

    try {
      const response = await axios.get(`/api/db/${dbName}/diagram_data`, {
        params: { type: diagramType },
      });

      if (response.data.success) {
        setDiagramData(response.data.data);

        // ✅ LOAD EXISTING RELATIONSHIPS
        const existingRelationships = response.data.data.relationships || [];
        setRelationships(
          existingRelationships.map((rel) => ({
            from: rel.from,
            to: rel.to,
            cardinality: rel.cardinality || "||--o{",
            column: rel.column,
            relationshipName: rel.relationshipName || rel.column || "",
          }))
        );
      } else {
        setError(response.data.error || "Failed to load diagram data");
      }
    } catch (err) {
      console.error("Failed to load diagram data:", err);
      setError(
        "Failed to load diagram data: " +
          (err.response?.data?.error || err.message)
      );
    } finally {
      setLoading(false);
    }
  };

  const generateMermaidCode = (data, type) => {
    let code = "";

    if (dbType === "sql") {
      if (type === "er") {
        code = generateERDiagram(data);
      } else if (type === "schema") {
        code = generateSchemaDiagram(data);
      }
    } else {
      if (type === "collections") {
        code = generateCollectionsDiagram(data);
      } else if (type === "hierarchy") {
        code = generateHierarchyDiagram(data);
      }
    }

    setDiagramCode(code);
    renderDiagram(code);
  };

  const sanitizeTableName = (name) => {
    return name.replace(/[^a-zA-Z0-9_]/g, "_").toUpperCase();
  };

  const generateERDiagram = (data) => {
    let code = "erDiagram\n";
    const tables = data.tables || [];

    tables.forEach((table) => {
      const tableName = sanitizeTableName(table.name);
      code += `    ${tableName} {\n`;

      const fields = table.fields || [];
      fields.forEach((field) => {
        let constraints = [];
        if (field.pk) constraints.push("PK");
        if (field.fk) constraints.push("FK");
        if (field.notnull) constraints.push("NOT NULL");

        const constraintStr =
          constraints.length > 0 ? ` "${constraints.join(",")}"` : "";
        code += `        ${field.type} ${field.name}${constraintStr}\n`;
      });
      code += "    }\n";
    });

    // ✅ USE CUSTOM RELATIONSHIPS (merged with existing ones)
    relationships.forEach((rel) => {
      const from = sanitizeTableName(rel.from);
      const to = sanitizeTableName(rel.to);
      const cardinality = rel.cardinality || "||--o{";
      const label = rel.relationshipName
        ? `"${rel.relationshipName}"`
        : rel.column
        ? `"via ${rel.column}"`
        : '"has"';
      code += `    ${from} ${cardinality} ${to} : ${label}\n`;
    });

    return code;
  };

  const generateSchemaDiagram = (data) => {
    let code = "graph LR\n";
    const tables = data.tables || [];

    tables.forEach((table, idx) => {
      const nodeId = `T${idx}`;
      const tableName = table.name || "unknown";
      const cols = table.fields?.length || 0;
      code += `    ${nodeId}["${tableName}<br/>${cols} columns"]\n`;

      if (idx < tables.length - 1) {
        code += `    ${nodeId} --> T${idx + 1}\n`;
      }
    });

    return code;
  };

  const generateCollectionsDiagram = (data) => {
    let code = "graph TB\n";
    const collections = data.collections || [];

    if (collections.length === 0) return "";

    code += `    DB["📦 Database: ${dbName}<br/>Collections: ${data.total_collections}<br/>Docs: ${data.total_documents}"]\n\n`;

    collections.forEach((coll, idx) => {
      const nodeId = "C" + idx;
      code += `    ${nodeId}["${coll.name}<br/>Docs:${coll.document_count} Keys:${coll.key_count}"]\n`;
      code += `    DB --> ${nodeId}\n`;
    });

    return code;
  };

  const generateHierarchyDiagram = (data) => {
    let code = "graph TB\n";
    const collections = data.collections || [];

    if (collections.length === 0) return "";

    collections.forEach((coll, idx) => {
      const collNodeId = "COLL" + idx;
      code += `    ${collNodeId}["📄 ${coll.name}<br/>(${coll.document_count} docs)"]\n`;

      const fields = coll.fields || {};
      let fieldIdx = 0;

      Object.entries(fields)
        .slice(0, 12)
        .forEach(([fieldName, fieldInfo]) => {
          const fieldNodeId = `F${idx}_${fieldIdx}`;
          code += `    ${fieldNodeId}["🔹 ${fieldName}<br/>(${fieldInfo.type})"]\n`;
          code += `    ${collNodeId} --> ${fieldNodeId}\n`;
          fieldIdx++;
        });
    });

    return code;
  };

  const handleAddRelationship = () => {
    if (!newRelationship.from || !newRelationship.to) {
      alert("Please select both tables");
      return;
    }

    if (newRelationship.from === newRelationship.to) {
      alert("Cannot create self-referencing relationship");
      return;
    }

    // Check for duplicate
    const isDuplicate = relationships.some(
      (rel) =>
        rel.from === newRelationship.from && rel.to === newRelationship.to
    );

    if (isDuplicate && editingRelationshipIndex === null) {
      alert("This relationship already exists");
      return;
    }

    if (editingRelationshipIndex !== null) {
      // Edit existing
      const updated = [...relationships];
      updated[editingRelationshipIndex] = { ...newRelationship };
      setRelationships(updated);
      setEditingRelationshipIndex(null);
    } else {
      // Add new
      setRelationships([...relationships, { ...newRelationship }]);
    }

    // Reset form and go back to list view
    setNewRelationship({
      from: "",
      to: "",
      cardinality: "||--o{",
      relationshipName: "",
    });
    setShowAddRelationshipForm(false);

    // Regenerate diagram
    setTimeout(() => {
      generateMermaidCode(diagramData, diagramType);
    }, 100);
  };

  const handleEditRelationship = (index) => {
    setNewRelationship({ ...relationships[index] });
    setEditingRelationshipIndex(index);
    setShowAddRelationshipForm(true);
  };

  const handleDeleteRelationship = (index) => {
    if (!window.confirm("Delete this relationship?")) return;

    const updated = relationships.filter((_, i) => i !== index);
    setRelationships(updated);

    // Regenerate diagram
    setTimeout(() => {
      generateMermaidCode(diagramData, diagramType);
    }, 100);
  };

  const handleCancelAddRelationship = () => {
    setNewRelationship({
      from: "",
      to: "",
      cardinality: "||--o{",
      relationshipName: "",
    });
    setEditingRelationshipIndex(null);
    setShowAddRelationshipForm(false);
  };

  const getCardinalityLabel = (cardinality) => {
    const labels = {
      "||--||": "One-to-One",
      "||--o{": "One-to-Many",
      "}o--o{": "Many-to-Many",
      "||--o|": "One-to-Zero-or-One",
    };
    return labels[cardinality] || cardinality;
  };

  const renderDiagram = async (code) => {
    if (!code) return;

    try {
      const uniqueId = `mermaid-${Date.now()}`;
      const { svg } = await mermaid.render(uniqueId, code);
      setDiagramSvg(svg);
    } catch (err) {
      console.error("Mermaid render error:", err);
      setError("Failed to render diagram: " + err.message);
    }
  };

  const downloadDiagram = () => {
    if (!diagramSvg) return;

    // Parse the SVG string
    const parser = new DOMParser();
    const svgDoc = parser.parseFromString(diagramSvg, "image/svg+xml");
    const svg = svgDoc.documentElement;

    // Remove any existing width/height that might be tiny
    svg.removeAttribute("width");
    svg.removeAttribute("height");

    // Get natural size from viewBox (Mermaid always sets this)
    const viewBox = svg.getAttribute("viewBox");
    let width = 1200;
    let height = 800;

    if (viewBox) {
      const parts = viewBox.trim().split(/\s+/).map(Number);
      if (parts.length === 4) {
        width = parts[2];
        height = parts[3];
      }
    }

    // Make it BIG and CRISP — 2.5× scale for royal quality
    const scale = 2.5;
    const finalWidth = Math.round(width * scale);
    const finalHeight = Math.round(height * scale);

    // Force the size
    svg.setAttribute("width", finalWidth);
    svg.setAttribute("height", finalHeight);

    // Ensure white background
    if (!svg.querySelector('rect[fill="white"]')) {
      const rect = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "rect"
      );
      rect.setAttribute("width", "100%");
      rect.setAttribute("height", "100%");
      rect.setAttribute("fill", "white");
      svg.insertBefore(rect, svg.firstChild);
    }

    // Serialize back to string
    const serializer = new XMLSerializer();
    const fixedSvg = serializer.serializeToString(svg);

    // Convert to base64 data URL (no taint ever)
    const dataUrl =
      "data:image/svg+xml;base64," +
      btoa(unescape(encodeURIComponent(fixedSvg)));

    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = finalWidth;
      canvas.height = finalHeight;

      const ctx = canvas.getContext("2d");
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";

      // White background (just in case)
      ctx.fillStyle = "white";
      ctx.fillRect(0, 0, finalWidth, finalHeight);

      // Draw the huge, crisp SVG
      ctx.drawImage(img, 0, 0, finalWidth, finalHeight);

      // Export ultra-sharp PNG
      canvas.toBlob(
        (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `${dbName}_${diagramType}_diagram.png`;
          a.click();
          URL.revokeObjectURL(url);
        },
        "image/png",
        1.0
      ); // max quality
    };

    img.src = dataUrl;
  };

  const getDescription = () => {
    const descriptions = {
      er: "📋 Visual representation of entities and their relationships in your database",
      schema:
        "📊 Overview of table structures, columns, and data types across your database",
      collections:
        "📦 Summary of all collections with document counts and fields",
      hierarchy: "🌳 Field-level structure and data types in each collection",
    };
    return descriptions[diagramType] || "";
  };

  return (
    <div>
      <h3 style={{ color: "#f0f0f0" }}>📊 Database Diagrams</h3>

      {error && (
        <div className="error" style={{ marginBottom: "15px" }}>
          {error}
        </div>
      )}

      {/* Diagram Controls */}
      <div
        style={{
          background: "#f8f8f8",
          padding: "25px",
          borderRadius: "12px",
          marginBottom: "20px",
        }}
      >
        <div style={{ marginBottom: "20px" }}>
          <label
            style={{
              fontWeight: "bold",
              display: "block",
              marginBottom: "10px",
              color: "#4b0082",
              fontSize: "1.05em",
            }}
          >
            📈 Select Diagram Type:
          </label>
          <select
            value={diagramType}
            onChange={(e) => setDiagramType(e.target.value)}
            style={{
              width: "100%",
              padding: "12px",
              border: "2px solid #9370db",
              borderRadius: "8px",
              fontSize: "15px",
              background: "white",
              cursor: "pointer",
              color: "#333",
            }}
          >
            {dbType === "sql" ? (
              <>
                <option value="er">Entity-Relationship (ER) Diagram</option>
                <option value="schema">Schema/Table Structure Diagram</option>
              </>
            ) : (
              <>
                <option value="collections">Collections Overview</option>
                <option value="hierarchy">Data Hierarchy Diagram</option>
              </>
            )}
          </select>
          <p
            style={{
              marginTop: "8px",
              fontSize: "0.9em",
              color: "#666",
              fontStyle: "italic",
            }}
          >
            {getDescription()}
          </p>
        </div>

        <div style={{ display: "flex", gap: "15px", justifyContent: "center" }}>
          <button
            onClick={() => generateMermaidCode(diagramData, diagramType)}
            disabled={loading || !diagramData}
            style={{
              padding: "14px 32px",
              background: loading
                ? "#ccc"
                : "linear-gradient(135deg, #6a5acd, #483d8b)",
              color: "white",
              border: "none",
              borderRadius: "10px",
              fontWeight: "bold",
              fontSize: "16px",
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "⏳ Loading..." : "🔄 Generate Diagram"}
          </button>

          {diagramSvg && (
            <button
              onClick={downloadDiagram}
              style={{
                padding: "14px 32px",
                background: "linear-gradient(135deg, #2e7d32, #1b5e20)",
                color: "white",
                border: "none",
                borderRadius: "10px",
                fontWeight: "bold",
                fontSize: "16px",
                cursor: "pointer",
              }}
            >
              💾 Download as Image
            </button>
          )}

          {diagramType === "er" && diagramData && (
            <button
              onClick={() => setShowRelationshipsModal(true)}
              style={{
                padding: "14px 32px",
                background: "linear-gradient(135deg, #e91e63, #ad1457)",
                color: "white",
                border: "none",
                borderRadius: "10px",
                fontWeight: "bold",
                fontSize: "16px",
                cursor: "pointer",
              }}
            >
              🔗 View Relationships
            </button>
          )}
        </div>
      </div>

      {/* Diagram Display */}
      {loading && (
        <div style={{ textAlign: "center", padding: "40px", color: "#6a5acd" }}>
          <div style={{ fontSize: "2.5em", marginBottom: "15px" }}>⏳</div>
          <p style={{ fontSize: "1.1em" }}>Generating diagram...</p>
        </div>
      )}

      {diagramSvg && !loading && (
        <div
          style={{
            background: "white",
            padding: "30px",
            borderRadius: "10px",
            boxShadow: "0 4px 15px rgba(0,0,0,0.1)",
            marginTop: "20px",
            overflowX: "auto",
          }}
        >
          <div dangerouslySetInnerHTML={{ __html: diagramSvg }} />
        </div>
      )}

      {diagramData && !loading && (
        <div
          style={{
            marginTop: "20px",
            padding: "20px",
            background: "#e8f5e9",
            borderLeft: "4px solid #4caf50",
            borderRadius: "5px",
          }}
        >
          <strong style={{ color: "#2e7d32", fontSize: "1.05em" }}>
            📊 Diagram Statistics:
          </strong>
          <div
            style={{ marginTop: "12px", color: "#1b5e20", lineHeight: "1.8" }}
          >
            {dbType === "sql" ? (
              <>
                <strong>Total Tables:</strong> {diagramData.tables?.length || 0}
                <br />
                <strong>Total Relationships:</strong> {relationships.length}
              </>
            ) : (
              <>
                <strong>Total Collections:</strong>{" "}
                {diagramData.total_collections || 0}
                <br />
                <strong>Total Documents:</strong>{" "}
                {diagramData.total_documents || 0}
              </>
            )}
          </div>
        </div>
      )}
      {/* ✅ RELATIONSHIPS MODAL */}
      {showRelationshipsModal && (
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
          onClick={() => {
            setShowRelationshipsModal(false);
            setShowAddRelationshipForm(false);
            setEditingRelationshipIndex(null);
            setNewRelationship({
              from: "",
              to: "",
              cardinality: "||--o{",
              relationshipName: "",
            });
          }}
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
              border: "2px solid #e91e63",
              boxShadow: "0 10px 40px rgba(233, 30, 99, 0.6)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {!showAddRelationshipForm ? (
              // ✅ VIEW RELATIONSHIPS LIST
              <>
                <h2
                  style={{
                    color: "#f0f0f0",
                    margin: "0 0 25px 0",
                    textAlign: "center",
                  }}
                >
                  🔗 Manage Relationships
                </h2>

                <button
                  onClick={() => setShowAddRelationshipForm(true)}
                  style={{
                    width: "100%",
                    padding: "14px",
                    background: "linear-gradient(135deg, #6a5acd, #483d8b)",
                    color: "white",
                    border: "none",
                    borderRadius: "8px",
                    cursor: "pointer",
                    fontWeight: "bold",
                    fontSize: "16px",
                    marginBottom: "20px",
                  }}
                >
                  ➕ Add Relationship
                </button>

                {relationships.length > 0 ? (
                  <div style={{ marginBottom: "20px" }}>
                    {relationships.map((rel, index) => (
                      <div
                        key={index}
                        style={{
                          background: "rgba(147, 112, 219, 0.15)",
                          padding: "15px",
                          borderRadius: "8px",
                          marginBottom: "10px",
                          border: "1px solid #9370db",
                        }}
                      >
                        <div
                          style={{
                            color: "#f0f0f0",
                            marginBottom: "8px",
                            fontSize: "15px",
                          }}
                        >
                          <strong>{rel.from}</strong>{" "}
                          {getCardinalityLabel(rel.cardinality)}{" "}
                          <strong>{rel.to}</strong>
                          {rel.relationshipName && (
                            <span
                              style={{ color: "#bb86fc", fontSize: "0.9em" }}
                            >
                              {" "}
                              ({rel.relationshipName})
                            </span>
                          )}
                        </div>
                        <div style={{ display: "flex", gap: "10px" }}>
                          <button
                            onClick={() => handleEditRelationship(index)}
                            style={{
                              flex: 1,
                              padding: "8px",
                              background: "#1e9530",
                              color: "white",
                              border: "none",
                              borderRadius: "5px",
                              cursor: "pointer",
                              fontWeight: "bold",
                            }}
                          >
                            ✏️ Edit
                          </button>
                          <button
                            onClick={() => handleDeleteRelationship(index)}
                            style={{
                              flex: 1,
                              padding: "8px",
                              background: "#dc3545",
                              color: "white",
                              border: "none",
                              borderRadius: "5px",
                              cursor: "pointer",
                              fontWeight: "bold",
                            }}
                          >
                            🗑️ Delete
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p
                    style={{
                      textAlign: "center",
                      color: "#ccc",
                      fontStyle: "italic",
                      padding: "20px",
                    }}
                  >
                    No relationships defined. Click "Add Relationship" to create
                    one.
                  </p>
                )}

                <button
                  onClick={() => {
                    setShowRelationshipsModal(false);
                    setShowAddRelationshipForm(false);
                  }}
                  style={{
                    width: "100%",
                    padding: "12px",
                    background: "#6c757d",
                    color: "white",
                    border: "none",
                    borderRadius: "8px",
                    cursor: "pointer",
                    fontWeight: "bold",
                  }}
                >
                  Close
                </button>
              </>
            ) : (
              // ✅ ADD/EDIT RELATIONSHIP FORM
              <>
                <h2
                  style={{
                    color: "#f0f0f0",
                    margin: "0 0 25px 0",
                    textAlign: "center",
                  }}
                >
                  {editingRelationshipIndex !== null ? "✏️ Edit" : "➕ Add"}{" "}
                  Relationship
                </h2>

                <div style={{ marginBottom: "20px" }}>
                  <label
                    style={{
                      display: "block",
                      marginBottom: "8px",
                      color: "#f0f0f0",
                      fontWeight: "bold",
                    }}
                  >
                    From Table:
                  </label>
                  <select
                    value={newRelationship.from}
                    onChange={(e) =>
                      setNewRelationship({
                        ...newRelationship,
                        from: e.target.value,
                      })
                    }
                    style={{
                      width: "100%",
                      padding: "12px",
                      border: "1.5px solid #9370db",
                      borderRadius: "8px",
                      background: "rgba(147, 112, 219, 0.15)",
                      color: "#f0f0f0",
                      fontSize: "14px",
                    }}
                  >
                    <option value="">-- Select Table --</option>
                    {diagramData?.tables?.map((table) => (
                      <option key={table.name} value={table.name}>
                        {table.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div style={{ marginBottom: "20px" }}>
                  <label
                    style={{
                      display: "block",
                      marginBottom: "8px",
                      color: "#f0f0f0",
                      fontWeight: "bold",
                    }}
                  >
                    Cardinality:
                  </label>
                  <select
                    value={newRelationship.cardinality}
                    onChange={(e) =>
                      setNewRelationship({
                        ...newRelationship,
                        cardinality: e.target.value,
                      })
                    }
                    style={{
                      width: "100%",
                      padding: "12px",
                      border: "1.5px solid #9370db",
                      borderRadius: "8px",
                      background: "rgba(147, 112, 219, 0.15)",
                      color: "#f0f0f0",
                      fontSize: "14px",
                    }}
                  >
                    <option value="||--||">One-to-One (||--||)</option>
                    <option value="||--o{">One-to-Many (||--o{"{"})</option>
                    <option value="}o--o{">
                      Many-to-Many ({"{"}o--o{"{"})
                    </option>
                    <option value="||--o|">One-to-Zero-or-One (||--o|)</option>
                  </select>
                </div>

                <div style={{ marginBottom: "20px" }}>
                  <label
                    style={{
                      display: "block",
                      marginBottom: "8px",
                      color: "#f0f0f0",
                      fontWeight: "bold",
                    }}
                  >
                    To Table:
                  </label>
                  <select
                    value={newRelationship.to}
                    onChange={(e) =>
                      setNewRelationship({
                        ...newRelationship,
                        to: e.target.value,
                      })
                    }
                    style={{
                      width: "100%",
                      padding: "12px",
                      border: "1.5px solid #9370db",
                      borderRadius: "8px",
                      background: "rgba(147, 112, 219, 0.15)",
                      color: "#f0f0f0",
                      fontSize: "14px",
                    }}
                  >
                    <option value="">-- Select Table --</option>
                    {diagramData?.tables?.map((table) => (
                      <option key={table.name} value={table.name}>
                        {table.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div style={{ marginBottom: "25px" }}>
                  <label
                    style={{
                      display: "block",
                      marginBottom: "8px",
                      color: "#f0f0f0",
                      fontWeight: "bold",
                    }}
                  >
                    Relationship Name (Optional):
                  </label>
                  <input
                    type="text"
                    value={newRelationship.relationshipName}
                    onChange={(e) =>
                      setNewRelationship({
                        ...newRelationship,
                        relationshipName: e.target.value.slice(0, 50), // max 50 chars
                      })
                    }
                    placeholder="e.g., 'manages', 'belongs to', 'has many'"
                    maxLength={50}
                    style={{
                      width: "100%",
                      padding: "12px",
                      border: "1.5px solid #9370db",
                      borderRadius: "8px",
                      background: "rgba(147, 112, 219, 0.15)",
                      color: "#f0f0f0",
                      fontSize: "14px",
                    }}
                  />
                  <small
                    style={{
                      color: "#bb86fc",
                      fontSize: "0.85em",
                      marginTop: "5px",
                      display: "block",
                    }}
                  >
                    Max 50 characters. Describes the relationship between
                    tables.
                  </small>
                </div>

                <div
                  style={{
                    display: "flex",
                    gap: "15px",
                    justifyContent: "flex-end",
                  }}
                >
                  <button
                    onClick={handleCancelAddRelationship}
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
                    onClick={handleAddRelationship}
                    style={{
                      padding: "14px 28px",
                      background: "#e91e63",
                      color: "white",
                      border: "none",
                      borderRadius: "8px",
                      cursor: "pointer",
                      fontWeight: "bold",
                    }}
                  >
                    {editingRelationshipIndex !== null ? "Update" : "Done"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default DiagramCreator;
