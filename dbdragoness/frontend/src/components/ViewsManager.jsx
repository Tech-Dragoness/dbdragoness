import React, { useState, useEffect } from "react";
import axios from "axios";

function ViewsManager({ dbName }) {
  const [views, setViews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newViewName, setNewViewName] = useState("");
  const [newViewQuery, setNewViewQuery] = useState("");
  const [selectedView, setSelectedView] = useState(null);
  const [viewDefinition, setViewDefinition] = useState("");
  const [supportsViews, setSupportsViews] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage] = useState(10);

  useEffect(() => {
    fetchViews();
  }, [dbName]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

  const fetchViews = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/api/db/${dbName}/views`);
      if (response.data.success) {
        setViews(response.data.views || []);
        setSupportsViews(response.data.supports_views || false);
      } else {
        setError(response.data.error || "Failed to fetch views");
      }
    } catch (err) {
      console.error("Failed to fetch views:", err);
      setError("Failed to load views");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateView = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    if (!newViewName.trim() || !newViewQuery.trim()) {
      setError("View name and query are required");
      return;
    }

    try {
      const response = await axios.post(`/api/db/${dbName}/views/create`, {
        view_name: newViewName,
        view_query: newViewQuery,
      });

      if (response.data.success) {
        setMessage(response.data.message);
        setNewViewName("");
        setNewViewQuery("");
        setShowCreateModal(false);
        fetchViews();
      } else {
        setError(response.data.error || "Failed to create view");
      }
    } catch (err) {
      setError(
        "Failed to create view: " + (err.response?.data?.error || err.message)
      );
    }
  };

  const handleDeleteView = async (viewName) => {
    if (!window.confirm(`Are you sure you want to delete view ${viewName}?`)) {
      return;
    }

    try {
      const response = await axios.post(`/api/db/${dbName}/views/delete`, {
        view_name: viewName,
      });

      if (response.data.success) {
        setMessage(response.data.message);
        setSelectedView(null);
        setViewDefinition("");
        fetchViews();
      } else {
        setError(response.data.error || "Failed to delete view");
      }
    } catch (err) {
      setError(
        "Failed to delete view: " + (err.response?.data?.error || err.message)
      );
    }
  };

  const handleViewClick = async (viewName) => {
    try {
      const response = await axios.get(
        `/api/db/${dbName}/view/${viewName}/definition`
      );

      if (response.data.success) {
        setSelectedView(viewName);
        setViewDefinition(response.data.definition);
      } else {
        setError(response.data.error || "Failed to fetch view definition");
      }
    } catch (err) {
      setError(
        "Failed to fetch view definition: " +
          (err.response?.data?.error || err.message)
      );
    }
  };

  if (loading) {
    return (
      <div style={{ padding: "20px", color: "#f0f0f0" }}>
        <div className="loading">Loading views...</div>
      </div>
    );
  }

  if (!supportsViews) {
    return (
      <div style={{ padding: "20px", color: "#f0f0f0" }}>
        <p style={{ textAlign: "center", fontStyle: "italic", color: "#666" }}>
          Views are not supported by this database handler.
        </p>
      </div>
    );
  }

  // Filter views based on search query (searches across all views)
  const filteredViews = views.filter((view) =>
    view.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Calculate pagination
  const totalPages = Math.ceil(filteredViews.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedViews = filteredViews.slice(startIndex, endIndex);

  return (
    <div style={{ padding: "20px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "20px",
        }}
      >
        <h3 style={{ margin: 0, color: "#f0f0f0" }}>Views in {dbName}</h3>
        <button
          onClick={() => setShowCreateModal(true)}
          style={{
            padding: "10px 20px",
            background: "#9370db",
            color: "white",
            border: "none",
            borderRadius: "5px",
            cursor: "pointer",
          }}
        >
          Create New View
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}

      {views.length > 0 ? (
        <div>
          <div style={{ marginBottom: "20px" }}>
            <input
              type="text"
              placeholder="Search views..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
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
            <div style={{ marginTop: "10px", color: "#999", fontSize: "14px" }}>
              Showing {startIndex + 1}-
              {Math.min(endIndex, filteredViews.length)} of{" "}
              {filteredViews.length} view{filteredViews.length !== 1 ? "s" : ""}
              {searchQuery && ` (filtered from ${views.length} total)`}
            </div>
          </div>

          {filteredViews.length > 0 ? (
            <>
              <table className="table-list">
                <thead>
                  <tr>
                    <th>View Name</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedViews.map((view) => (
                    <tr key={view.name}>
                      <td>
                        <strong>{view.name}</strong>
                      </td>
                      <td>
                        <button
                          onClick={() => handleViewClick(view.name)}
                          style={{ background: "#1e9530", marginRight: "10px" }}
                        >
                          View Definition
                        </button>
                        <button
                          onClick={() => handleDeleteView(view.name)}
                          style={{ background: "#dc3545" }}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {totalPages > 1 && (
                <div
                  style={{
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    gap: "10px",
                    marginTop: "20px",
                  }}
                >
                  <button
                    onClick={() =>
                      setCurrentPage((prev) => Math.max(1, prev - 1))
                    }
                    disabled={currentPage === 1}
                    style={{
                      padding: "8px 15px",
                      background: currentPage === 1 ? "#555" : "#9370db",
                      color: "white",
                      border: "none",
                      borderRadius: "5px",
                      cursor: currentPage === 1 ? "not-allowed" : "pointer",
                    }}
                  >
                    Previous
                  </button>

                  <span style={{ color: "#f0f0f0" }}>
                    Page {currentPage} of {totalPages}
                  </span>

                  <button
                    onClick={() =>
                      setCurrentPage((prev) => Math.min(totalPages, prev + 1))
                    }
                    disabled={currentPage === totalPages}
                    style={{
                      padding: "8px 15px",
                      background:
                        currentPage === totalPages ? "#555" : "#9370db",
                      color: "white",
                      border: "none",
                      borderRadius: "5px",
                      cursor:
                        currentPage === totalPages ? "not-allowed" : "pointer",
                    }}
                  >
                    Next
                  </button>
                </div>
              )}

              {selectedView && viewDefinition && (
                <div
                  style={{
                    marginTop: "30px",
                    background: "rgba(147, 112, 219, 0.1)",
                    padding: "20px",
                    borderRadius: "10px",
                  }}
                >
                  <h4 style={{ color: "#f0f0f0" }}>
                    View Definition: {selectedView}
                  </h4><br></br>
                  <pre
                    style={{
                      background: "rgba(30, 0, 51, 0.5)",
                      padding: "15px",
                      borderRadius: "5px",
                      color: "#f0f0f0",
                      overflowX: "auto",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}
                  >
                    {viewDefinition}
                  </pre>
                </div>
              )}
            </>
          ) : (
            <p
              style={{
                textAlign: "center",
                fontStyle: "italic",
                color: "#666",
              }}
            >
              No views match your search.
            </p>
          )}
        </div>
      ) : (
        <p style={{ textAlign: "center", fontStyle: "italic", color: "#666" }}>
          No views found.
        </p>
      )}

      {showCreateModal && (
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
            <h3 style={{ color: "#f0f0f0", marginTop: 0 }}>Create New View</h3>

            <form onSubmit={handleCreateView}>
              <div style={{ marginBottom: "20px" }}>
                <label
                  style={{
                    display: "block",
                    color: "#f0f0f0",
                    marginBottom: "5px",
                  }}
                >
                  View Name:
                </label>
                <input
                  type="text"
                  value={newViewName}
                  onChange={(e) => setNewViewName(e.target.value)}
                  placeholder="e.g., active_users_view"
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
                    marginBottom: "5px",
                  }}
                >
                  View Query (SELECT statement):
                </label>
                <textarea
                  value={newViewQuery}
                  onChange={(e) => setNewViewQuery(e.target.value)}
                  placeholder="SELECT column1, column2 FROM table_name WHERE condition"
                  required
                  rows={8}
                  style={{
                    width: "100%",
                    padding: "10px",
                    border: "1.5px solid #9370db",
                    borderRadius: "5px",
                    background: "rgba(30, 0, 51, 0.5)",
                    color: "#f0f0f0",
                    fontSize: "14px",
                    fontFamily: "monospace",
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
                  onClick={() => {
                    setShowCreateModal(false);
                    setNewViewName("");
                    setNewViewQuery("");
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
                  Create View
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default ViewsManager;
