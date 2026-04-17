import React, { useState, useEffect, useRef } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  RadarController,
  RadialLinearScale,
  PolarAreaController,
  Title,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Bar, Line, Pie, Doughnut, Radar, PolarArea } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  RadarController,
  RadialLinearScale,
  PolarAreaController,
  Title,
  Tooltip,
  Legend,
  Filler
);

function ChartCreator({ chartData, chartKeys }) {
  const [chartType, setChartType] = useState("bar");
  const [labelField, setLabelField] = useState("");
  const [dataFields, setDataFields] = useState([]);
  const [multiMode, setMultiMode] = useState("grouped");
  const [chartConfig, setChartConfig] = useState(null);
  const [stats, setStats] = useState([]);
  const [error, setError] = useState("");
  const chartRef = useRef(null);
  
  // New merging states
  const [enableMerging, setEnableMerging] = useState(false);
  const [mergeStrategy, setMergeStrategy] = useState("sum");
  const [duplicateCounts, setDuplicateCounts] = useState({});

  useEffect(() => {
    if (chartKeys.length > 0 && !labelField) {
      setLabelField(chartKeys[0]);
    }
  }, [chartKeys, labelField]);

  useEffect(() => {
    setError("");
    setStats([]);

    const isPieLike = ["pie", "doughnut", "polarArea"].includes(chartType);

    if (isPieLike && dataFields.length > 1) {
      setChartConfig(null);
      setError(
        `✨ ${chartType.charAt(0).toUpperCase() + chartType.slice(1)} charts can only show ONE data field at a time. ` +
          `Your ${dataFields.length} selected Y fields are safely kept — please pick either only 1 Y field or change chart type`
      );
      return;
    }

    if (labelField && dataFields.length > 0) {
      generateChart();
    } else {
      setChartConfig(null);
    }

    if (!isPieLike && multiMode !== "grouped" && multiMode !== "stacked" && multiMode !== "overlapping") {
      setMultiMode("grouped");
    }
  }, [chartType, labelField, dataFields, multiMode, enableMerging, mergeStrategy]);

  const mergeDataByLabel = (data, labelField, dataFields, strategy) => {
    const grouped = {};
    const counts = {};
    
    data.forEach((row) => {
      const label = String(row[labelField] || "null");
      
      if (!grouped[label]) {
        grouped[label] = { count: 0, values: {} };
        counts[label] = 0;
        dataFields.forEach(field => {
          grouped[label].values[field] = [];
        });
      }
      
      grouped[label].count++;
      counts[label]++;
      dataFields.forEach(field => {
        const val = parseFloat(row[field]);
        if (!isNaN(val)) {
          grouped[label].values[field].push(val);
        }
      });
    });

    setDuplicateCounts(counts);

    const mergedData = [];
    Object.keys(grouped).forEach(label => {
      const entry = { [labelField]: label };
      
      dataFields.forEach(field => {
        const values = grouped[label].values[field];
        if (values.length === 0) {
          entry[field] = 0;
          return;
        }
        
        switch (strategy) {
          case "sum":
            entry[field] = values.reduce((a, b) => a + b, 0);
            break;
          case "average":
            entry[field] = values.reduce((a, b) => a + b, 0) / values.length;
            break;
          case "max":
            entry[field] = Math.max(...values);
            break;
          case "min":
            entry[field] = Math.min(...values);
            break;
          case "first":
            entry[field] = values[0];
            break;
          case "last":
            entry[field] = values[values.length - 1];
            break;
          case "keepSame":
            const allSame = values.every(v => v === values[0]);
            entry[field] = allSame ? values[0] : values.reduce((a, b) => a + b, 0) / values.length;
            break;
          default:
            entry[field] = values.reduce((a, b) => a + b, 0);
        }
      });
      
      mergedData.push(entry);
    });
    
    return mergedData;
  };

  const generateChart = () => {
    setError("");
    setStats([]);

    if (!labelField) {
      setError("Please select a label field (X-axis)");
      return;
    }
    if (dataFields.length === 0) {
      setError("Please select at least one data field (Y-axis)");
      return;
    }

    const isPieLike = ["pie", "doughnut", "polarArea"].includes(chartType);
    if (isPieLike && dataFields.length > 1) {
      setError(`Only ONE data field allowed for ${chartType} charts`);
      return;
    }

    // Apply merging if enabled
    const processedData = enableMerging 
      ? mergeDataByLabel(chartData, labelField, dataFields, mergeStrategy)
      : chartData;

    if (!enableMerging) {
      setDuplicateCounts({});
    }

    const labels = processedData.map((row) => String(row[labelField] || "null"));

    const baseColors = [
      "rgba(106, 90, 205, ",
      "rgba(255, 99, 132, ",
      "rgba(54, 162, 235, ",
      "rgba(255, 206, 86, ",
      "rgba(75, 192, 192, ",
      "rgba(153, 102, 255, ",
      "rgba(255, 159, 64, ",
      "rgba(199, 199, 199, ",
      "rgba(83, 102, 255, ",
      "rgba(255, 99, 255, ",
    ];

    const opacity = multiMode === "overlapping" ? 0.5 : 0.8;
    const isStacked = multiMode === "stacked";

    const datasets = dataFields.map((field, i) => {
      const values = processedData.map((row) => {
        const val = parseFloat(row[field]);
        return isNaN(val) ? 0 : val;
      });

      const base = baseColors[i % baseColors.length];

      const shouldFill = chartType === "radar" || (chartType === "line" && isStacked);

      const backgroundColors = isPieLike
        ? values.map((_, idx) => baseColors[idx % baseColors.length] + opacity + ")")
        : base + (shouldFill ? "0.3)" : opacity + ")");

      const borderColors = isPieLike
        ? values.map((_, idx) => baseColors[idx % baseColors.length] + "1)")
        : base + "1)";

      return {
        label: field,
        data: values,
        backgroundColor: backgroundColors,
        borderColor: borderColors,
        borderWidth: multiMode === "overlapping" ? 2 : 3,
        pointBackgroundColor: base + "1)",
        pointRadius: multiMode === "overlapping" ? 4 : 5,
        pointHoverRadius: 7,
        tension: chartType === "line" ? 0.4 : 0,
        fill: shouldFill,
        spanGaps: false,
        barPercentage: multiMode === "overlapping" ? 1.0 : 0.9,
        categoryPercentage: multiMode === "overlapping" ? 1.0 : 0.8,
      };
    });

    const config = {
      type: chartType,
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { 
          mode: multiMode === "overlapping" ? "point" : "index", 
          intersect: multiMode === "overlapping" 
        },
        plugins: {
          legend: {
            display: dataFields.length <= 10,
            position: "top",
            labels: {
              font: { family: "'Courier New', monospace", size: 14 },
              usePointStyle: true,
              pointStyle: "circle",
              padding: 20,
              color: "#333",
              boxWidth: 15,
              boxHeight: 15,
            },
          },
          title: {
            display: true,
            text: `${chartType.charAt(0).toUpperCase() + chartType.slice(1)} Chart • ${processedData.length} records${enableMerging ? ' (merged)' : ''}`,
            font: {
              size: 20,
              weight: "bold",
              family: "'Courier New', monospace",
            },
            color: "#4b0082",
            padding: 30,
          },
          tooltip: {
            backgroundColor: "rgba(0,0,0,0.8)",
            cornerRadius: 8,
            padding: 12,
            callbacks: {
              afterLabel: (context) => {
                if (enableMerging) {
                  const label = context.label;
                  const count = duplicateCounts[label] || 1;
                  if (count > 1) {
                    return `📊 Merged from ${count} records`;
                  }
                }
                return '';
              },
              footer: (items) => {
                if (isStacked && items.length > 1) {
                  const total = items.reduce((sum, item) => sum + item.parsed.y, 0);
                  return `Total: ${total.toFixed(2)}`;
                }
                return "";
              },
            },
          },
        },
        scales: isPieLike
          ? {}
          : {
              r: chartType === "radar" ? {
                  beginAtZero: true,
                  angleLines: { color: "rgba(0,0,0,0.1)" },
                  grid: { color: "rgba(0,0,0,0.1)" },
                  pointLabels: {
                    font: { size: 13 },
                    color: "#333",
                  },
                  ticks: {
                    backdropColor: "transparent",
                    color: "#666",
                  },
                } : undefined,
              x: chartType !== "radar" ? {
                  stacked: isStacked,
                  ticks: {
                    autoSkip: false,
                    maxRotation: 45,
                    minRotation: 45,
                    font: { size: 11 },
                    callback: function (value, index, ticks) {
                      const label = this.getLabelForValue(value);
                      const maxLength = 15;
                      if (label.length > maxLength) {
                        return label.substring(0, maxLength) + "...";
                      }
                      return label;
                    },
                  },
                } : undefined,
              y: chartType !== "radar" ? { 
                  stacked: isStacked, 
                  beginAtZero: true 
                } : undefined,
            },
      },
    };

    setChartConfig(config);
    generateStats(processedData);
  };

  const generateStats = (data) => {
    let statsArray = [];

    statsArray.push({
      label: "Total Records",
      value: data.length,
    });

    dataFields.forEach((field) => {
      const values = data
        .map((r) => parseFloat(r[field]))
        .filter((v) => !isNaN(v));
      if (values.length === 0) return;
      const sum = values.reduce((a, b) => a + b, 0);
      const avg = (sum / values.length).toFixed(2);
      const max = Math.max(...values);
      const min = Math.min(...values);

      statsArray.push({
        label: field,
        stats: {
          sum: sum.toFixed(2),
          avg: avg,
          max: max,
          min: min,
        },
      });
    });

    setStats(statsArray);
  };

  const downloadChart = () => {
    if (!chartRef.current) return;

    const canvas = chartRef.current.canvas;
    const scaleFactor = Math.max(1, Math.min(2, 3000 / Math.max(canvas.width, canvas.height)));

    const tempCanvas = document.createElement("canvas");
    tempCanvas.width = canvas.width * scaleFactor;
    tempCanvas.height = canvas.height * scaleFactor;
    const ctx = tempCanvas.getContext("2d");

    ctx.fillStyle = "white";
    ctx.fillRect(0, 0, tempCanvas.width, tempCanvas.height);
    ctx.scale(scaleFactor, scaleFactor);
    ctx.drawImage(canvas, 0, 0);

    tempCanvas.toBlob((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `chart_${Date.now()}.png`;
      a.click();
      URL.revokeObjectURL(url);
    });
  };

  const getChartComponent = () => {
    if (!chartConfig) return null;
    const props = {
      ref: chartRef,
      data: chartConfig.data,
      options: chartConfig.options,
    };
    switch (chartType) {
      case "bar": return <Bar {...props} />;
      case "line": return <Line {...props} />;
      case "pie": return <Pie {...props} />;
      case "doughnut": return <Doughnut {...props} />;
      case "radar": return <Radar {...props} />;
      case "polarArea": return <PolarArea {...props} />;
      default: return <Bar {...props} />;
    }
  };

  const showMultiMode = !["pie", "doughnut", "polarArea"].includes(chartType);

  return (
    <div style={{ padding: "20px", fontFamily: "Arial, sans-serif" }}>
      <h3 style={{ color: "#f0f0f0", margin: "0 0 25px 0" }}>Chart Creator</h3>

      {error && (
        <div style={{
          padding: "16px",
          background: "#ffe6e6",
          borderLeft: "5px solid #dc3545",
          borderRadius: "8px",
          marginBottom: "20px",
          color: "#721c24",
          fontWeight: "bold",
        }}>
          {error}
        </div>
      )}

      <div style={{
        background: "#f8f8f8",
        padding: "30px",
        borderRadius: "12px",
        color: "#333",
      }}>
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "25px",
          marginBottom: "25px",
        }}>
          <div>
            <label style={{
              fontWeight: "bold",
              display: "block",
              marginBottom: "10px",
              color: "#4b0082",
            }}>
              Chart Type:
            </label>
            <select
              value={chartType}
              onChange={(e) => setChartType(e.target.value)}
              style={{
                width: "100%",
                padding: "12px",
                border: "2px solid #9370db",
                borderRadius: "8px",
                fontSize: "15px",
                background: "#3a2f4c",
                color: "#f0f0f0",
              }}
            >
              <option value="bar">Bar Chart</option>
              <option value="line">Line Chart</option>
              <option value="pie">Pie Chart</option>
              <option value="doughnut">Doughnut Chart</option>
              <option value="radar">Radar Chart</option>
              <option value="polarArea">Polar Area Chart</option>
            </select>
          </div>

          <div>
            <label style={{
              fontWeight: "bold",
              display: "block",
              marginBottom: "10px",
              color: "#4b0082",
            }}>
              Label Field (X-Axis / Categories):
            </label>
            <select
              value={labelField}
              onChange={(e) => setLabelField(e.target.value)}
              style={{
                width: "100%",
                padding: "12px",
                border: "2px solid #9370db",
                borderRadius: "8px",
                fontSize: "15px",
                background: "#3a2f4c",
                color: "#f0f0f0",
              }}
            >
              <option value="">-- Select Label Field --</option>
              {chartKeys.map((key) => (
                <option key={key} value={key}>{key}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Duplicate Merging Section */}
        <div style={{
          margin: "25px 0",
          padding: "18px",
          background: "#fff3cd",
          borderRadius: "10px",
          borderLeft: "5px solid #ffc107",
        }}>
          <label style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: "10px" }}>
            <input
              type="checkbox"
              checked={enableMerging}
              onChange={(e) => setEnableMerging(e.target.checked)}
              style={{ width: "18px", height: "18px" }}
            />
            <strong style={{ color: "#856404" }}>Merge Duplicate X-Axis Values</strong>
          </label>
          
          {enableMerging && (
            <div style={{ marginTop: "15px" }}>
              <label style={{ 
                display: "block", 
                marginBottom: "8px", 
                color: "#856404",
                fontSize: "0.95em"
              }}>
                Merge Strategy for Y-Values:
              </label>
              <select
                value={mergeStrategy}
                onChange={(e) => setMergeStrategy(e.target.value)}
                style={{
                  padding: "10px",
                  border: "2px solid #ffc107",
                  borderRadius: "6px",
                  fontSize: "14px",
                  background: "white",
                  color: "#333",
                  width: "100%",
                }}
              >
                <option value="sum">Sum - Add all values together</option>
                <option value="average">Average - Calculate mean of values</option>
                <option value="max">Maximum - Keep highest value</option>
                <option value="min">Minimum - Keep lowest value</option>
                <option value="first">First - Use first occurrence</option>
                <option value="last">Last - Use last occurrence</option>
                <option value="keepSame">Keep Same - If identical keep it, else average</option>
              </select>
            </div>
          )}
        </div>

        {showMultiMode && (
          <div style={{
            margin: "25px 0",
            padding: "18px",
            background: "#e8f5e9",
            borderRadius: "10px",
            borderLeft: "5px solid #4caf50",
          }}>
            <strong style={{ color: "#2e7d32" }}>Multiple Dataset Display Mode:</strong>
            <div style={{
              display: "flex",
              gap: "25px",
              marginTop: "15px",
              flexWrap: "wrap",
            }}>
              {["grouped", "stacked", "overlapping"].map((mode) => (
                <label key={mode} style={{
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                }}>
                  <input
                    type="radio"
                    name="multiMode"
                    value={mode}
                    checked={multiMode === mode}
                    onChange={(e) => setMultiMode(e.target.value)}
                  />
                  <span style={{ textTransform: "capitalize", fontWeight: "bold" }}>
                    {mode}
                  </span>
                </label>
              ))}
            </div>
            <p style={{
              margin: "12px 0 0",
              fontSize: "0.9em",
              color: "#1b5e20",
              fontStyle: "italic",
            }}>
              {multiMode === "grouped" && "Side-by-side bars — best for comparison"}
              {multiMode === "stacked" && "Stacked — shows totals and parts"}
              {multiMode === "overlapping" && "Transparent overlay — reveals patterns and overlap"}
            </p>
          </div>
        )}

        <div style={{ margin: "25px 0" }}>
          <label style={{
            fontWeight: "bold",
            display: "block",
            marginBottom: "12px",
            color: "#4b0082",
          }}>
            Data Fields (Y-Axis / Values):
            <span style={{
              fontWeight: "normal",
              color: "#666",
              fontSize: "0.9em",
              marginLeft: "12px",
            }}>
              {showMultiMode ? "(Select one or more)" : "(Select ONE numeric field)"}
            </span>
          </label>
          <div style={{
            background: "white",
            border: "2px solid #9370db",
            borderRadius: "8px",
            padding: "15px",
            maxHeight: "220px",
            overflowY: "auto",
          }}>
            {chartKeys.map((key) => (
              <div key={key} style={{ margin: "10px 0" }}>
                <label style={{
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                }}>
                  <input
                    type="checkbox"
                    checked={dataFields.includes(key)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        if (!showMultiMode) {
                          setDataFields([key]);
                        } else {
                          setDataFields((prev) => [...prev, key]);
                        }
                      } else {
                        setDataFields((prev) => prev.filter((f) => f !== key));
                      }
                    }}
                    style={{ marginRight: "12px" }}
                  />
                  <span>{key}</span>
                </label>
              </div>
            ))}
          </div>
        </div>

        <div style={{
          display: "flex",
          gap: "20px",
          justifyContent: "center",
          marginTop: "30px",
        }}>
          <button
            onClick={generateChart}
            style={{
              padding: "14px 35px",
              background: "linear-gradient(135deg, #6a5acd, #483d8b)",
              color: "white",
              border: "none",
              borderRadius: "10px",
              fontWeight: "bold",
              fontSize: "16px",
              cursor: "pointer",
              boxShadow: "0 6px 20px rgba(106,90,205,0.4)",
              transition: "all 0.3s",
            }}
            onMouseOver={(e) => (e.target.style.transform = "translateY(-3px)")}
            onMouseOut={(e) => (e.target.style.transform = "")}
          >
            Generate Chart
          </button>

          {chartConfig && (
            <button
              onClick={downloadChart}
              style={{
                padding: "14px 35px",
                background: "linear-gradient(135deg, #2e7d32, #1b5e20)",
                color: "white",
                border: "none",
                borderRadius: "10px",
                fontWeight: "bold",
                fontSize: "16px",
                cursor: "pointer",
              }}
            >
              Download as Image
            </button>
          )}
        </div>
      </div>

      {chartConfig && (
        <div style={{
          background: "white",
          padding: "40px",
          borderRadius: "12px",
          marginTop: "35px",
          boxShadow: "0 8px 25px rgba(0,0,0,0.15)",
          minHeight: "600px",
          height: Math.max(600, chartData.length * 15) + "px",
          maxHeight: "1200px",
          overflowY: "auto",
          overflowX: "auto",
        }}>
          {dataFields.length > 10 && (
            <div style={{
              maxHeight: "150px",
              overflowY: "auto",
              overflowX: "hidden",
              marginBottom: "20px",
              padding: "15px",
              background: "#f9f9f9",
              borderRadius: "8px",
              border: "1px solid #ddd",
            }}>
              <strong style={{
                color: "#4b0082",
                display: "block",
                marginBottom: "10px",
              }}>
                Legend ({dataFields.length} fields):
              </strong>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "15px" }}>
                {chartConfig.data.datasets.map((dataset, idx) => (
                  <div key={idx} style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                  }}>
                    <div style={{
                      width: "20px",
                      height: "20px",
                      background: Array.isArray(dataset.backgroundColor)
                        ? dataset.backgroundColor[0]
                        : dataset.backgroundColor,
                      borderRadius: "50%",
                      border: `2px solid ${Array.isArray(dataset.borderColor)
                        ? dataset.borderColor[0]
                        : dataset.borderColor}`,
                    }} />
                    <span style={{ fontSize: "13px", color: "#333" }}>
                      {dataset.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{
            minHeight: "600px",
            height: Math.max(600, chartData.length * 15) + "px",
            maxHeight: "1200px",
            overflowY: "auto",
            overflowX: "auto",
          }}>
            <div style={{ minHeight: "500px", height: "100%" }}>
              {getChartComponent()}
            </div>
          </div>
        </div>
      )}

      {stats.length > 0 && (
        <div style={{
          marginTop: "40px",
          padding: "25px",
          background: "#e8f5e9",
          borderLeft: "6px solid #4caf50",
          borderRadius: "10px",
        }}>
          <strong style={{ color: "#2e7d32", fontSize: "1.1em" }}>
            Chart Statistics:
          </strong>
          <div style={{ marginTop: "15px", color: "#1b5e20", lineHeight: "1.7" }}>
            {stats.map((stat, idx) => (
              <div key={idx} style={{ marginBottom: "15px" }}>
                {stat.stats ? (
                  <>
                    <strong>{stat.label}:</strong>
                    <div style={{ marginLeft: "20px", marginTop: "5px" }}>
                      • Sum: {stat.stats.sum}<br />
                      • Average: {stat.stats.avg}<br />
                      • Max: {stat.stats.max}<br />
                      • Min: {stat.stats.min}
                    </div>
                  </>
                ) : (
                  <>
                    <strong>{stat.label}:</strong> {stat.value}
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default ChartCreator;