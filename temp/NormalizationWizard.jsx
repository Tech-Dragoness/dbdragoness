import React, { useState } from 'react';
import axios from 'axios';

function NormalizationWizard({ dbName }) {
  const [step, setStep] = useState(1);
  const [normalForm, setNormalForm] = useState('');
  const [analysis, setAnalysis] = useState(null);
  const [answers, setAnswers] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [result, setResult] = useState(null);

  const normalForms = [
    { value: '1NF', label: 'First Normal Form (1NF)', description: 'Eliminate repeating groups' },
    { value: '2NF', label: 'Second Normal Form (2NF)', description: 'Remove partial dependencies' },
    { value: '3NF', label: 'Third Normal Form (3NF)', description: 'Remove transitive dependencies' },
    { value: 'BCNF', label: 'Boyce-Codd Normal Form (BCNF)', description: 'Stricter version of 3NF' }
  ];

  const fetchAnalysis = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/api/db/${dbName}/analyze_for_normalization`);
      
      if (response.data.success) {
        setAnalysis(response.data.analysis);
        setStep(2);
      } else {
        setError(response.data.error || 'Failed to analyze database');
      }
    } catch (err) {
      setError('Failed to analyze database: ' + (err.response?.data?.error || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleNormalize = async () => {
    if (!normalForm) {
      setError('Please select a normal form');
      return;
    }

    try {
      setLoading(true);
      const response = await axios.post(`/api/db/${dbName}/normalize`, {
        normal_form: normalForm,
        analysis_data: {
          ...analysis,
          user_answers: answers
        }
      });

      if (response.data.success) {
        setResult(response.data);
        setMessage(response.data.message);
        setStep(4);
      } else {
        setError(response.data.error || 'Normalization failed');
      }
    } catch (err) {
      setError('Normalization failed: ' + (err.response?.data?.error || err.message));
    } finally {
      setLoading(false);
    }
  };

  const updateAnswer = (questionKey, value) => {
    setAnswers({ ...answers, [questionKey]: value });
  };

  return (
    <div style={{ padding: '20px' }}>
      <h3 style={{ color: '#f0f0f0', marginBottom: '20px' }}>Database Normalization Wizard</h3>

      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}

      {step === 1 && (
        <div>
          <p style={{ color: '#ccc', marginBottom: '20px' }}>
            This wizard will help you normalize your database structure. Select the desired normal form and answer questions about your data.
          </p>

          <div style={{ marginBottom: '30px' }}>
            <label style={{ display: 'block', color: '#f0f0f0', marginBottom: '10px', fontWeight: 'bold' }}>
              Select Target Normal Form:
            </label>
            {normalForms.map((nf) => (
              <div
                key={nf.value}
                onClick={() => setNormalForm(nf.value)}
                style={{
                  padding: '15px',
                  marginBottom: '10px',
                  background: normalForm === nf.value ? 'rgba(147, 112, 219, 0.3)' : 'rgba(30, 0, 51, 0.3)',
                  border: normalForm === nf.value ? '2px solid #9370db' : '1px solid #555',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => {
                  if (normalForm !== nf.value) {
                    e.currentTarget.style.background = 'rgba(147, 112, 219, 0.2)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (normalForm !== nf.value) {
                    e.currentTarget.style.background = 'rgba(30, 0, 51, 0.3)';
                  }
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '5px' }}>
                  <input
                    type="radio"
                    checked={normalForm === nf.value}
                    onChange={() => setNormalForm(nf.value)}
                    style={{ marginRight: '10px', width: '18px', height: '18px' }}
                  />
                  <span style={{ color: '#f0f0f0', fontWeight: 'bold' }}>{nf.label}</span>
                </div>
                <p style={{ color: '#aaa', margin: '0 0 0 28px', fontSize: '14px' }}>
                  {nf.description}
                </p>
              </div>
            ))}
          </div>

          <button
            onClick={fetchAnalysis}
            disabled={!normalForm || loading}
            style={{
              padding: '12px 30px',
              background: !normalForm || loading ? '#6c757d' : '#9370db',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: !normalForm || loading ? 'not-allowed' : 'pointer',
              fontSize: '16px',
              fontWeight: 'bold'
            }}
          >
            {loading ? 'Analyzing...' : 'Next: Analyze Database'}
          </button>
        </div>
      )}

      {step === 2 && analysis && (
        <div>
          <h4 style={{ color: '#f0f0f0', marginBottom: '20px' }}>Analysis Results</h4>
          
          <div style={{ background: 'rgba(147, 112, 219, 0.1)', padding: '20px', borderRadius: '10px', marginBottom: '20px' }}>
            <p style={{ color: '#f0f0f0' }}>
              <strong>Current State:</strong> Database analyzed for {normalForm} normalization
            </p>
            {analysis.issues && analysis.issues.length > 0 && (
              <div style={{ marginTop: '15px' }}>
                <p style={{ color: '#f0f0f0', fontWeight: 'bold' }}>Detected Issues:</p>
                <ul style={{ color: '#ccc' }}>
                  {analysis.issues.map((issue, index) => (
                    <li key={index}>{issue}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <button
            onClick={() => setStep(3)}
            style={{
              padding: '12px 30px',
              background: '#9370db',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer',
              fontSize: '16px',
              fontWeight: 'bold',
              marginRight: '10px'
            }}
          >
            Next: Answer Questions
          </button>
          <button
            onClick={() => setStep(1)}
            style={{
              padding: '12px 30px',
              background: '#6c757d',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer',
              fontSize: '16px'
            }}
          >
            Back
          </button>
        </div>
      )}

      {step === 3 && analysis && (
        <div>
          <h4 style={{ color: '#f0f0f0', marginBottom: '20px' }}>Answer Questions About Your Data</h4>
          
          <div style={{ background: 'rgba(147, 112, 219, 0.1)', padding: '20px', borderRadius: '10px', marginBottom: '20px' }}>
            <p style={{ color: '#ccc', marginBottom: '15px' }}>
              To help normalize your database effectively, please answer the following questions:
            </p>

            {/* Question 1: Repeating Groups */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ color: '#f0f0f0', fontWeight: 'bold', display: 'block', marginBottom: '10px' }}>
                1. Do any tables have repeating groups or multi-valued attributes?
              </label>
              <p style={{ color: '#999', fontSize: '0.9em', marginBottom: '10px' }}>
                (e.g., multiple phone numbers in one column, comma-separated values)
              </p>
              <div style={{ display: 'flex', gap: '15px' }}>
                <label style={{ color: '#f0f0f0', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="repeating_groups"
                    value="yes"
                    checked={answers.repeating_groups === 'yes'}
                    onChange={(e) => updateAnswer('repeating_groups', e.target.value)}
                    style={{ marginRight: '8px' }}
                  />
                  Yes
                </label>
                <label style={{ color: '#f0f0f0', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="repeating_groups"
                    value="no"
                    checked={answers.repeating_groups === 'no'}
                    onChange={(e) => updateAnswer('repeating_groups', e.target.value)}
                    style={{ marginRight: '8px' }}
                  />
                  No
                </label>
              </div>
              {answers.repeating_groups === 'yes' && (
                <textarea
                  placeholder="Please describe which tables and columns..."
                  value={answers.repeating_groups_details || ''}
                  onChange={(e) => updateAnswer('repeating_groups_details', e.target.value)}
                  rows={3}
                  style={{
                    marginTop: '10px',
                    width: '100%',
                    padding: '8px',
                    border: '1.5px solid #9370db',
                    borderRadius: '5px',
                    background: 'rgba(30, 0, 51, 0.5)',
                    color: '#f0f0f0',
                  }}
                />
              )}
            </div>

            {/* Question 2: Partial Dependencies */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ color: '#f0f0f0', fontWeight: 'bold', display: 'block', marginBottom: '10px' }}>
                2. Are there columns that depend on only part of a composite primary key?
              </label>
              <p style={{ color: '#999', fontSize: '0.9em', marginBottom: '10px' }}>
                (e.g., in a table with keys [order_id, product_id], if product_name depends only on product_id)
              </p>
              <div style={{ display: 'flex', gap: '15px' }}>
                <label style={{ color: '#f0f0f0', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="partial_dependencies"
                    value="yes"
                    checked={answers.partial_dependencies === 'yes'}
                    onChange={(e) => updateAnswer('partial_dependencies', e.target.value)}
                    style={{ marginRight: '8px' }}
                  />
                  Yes
                </label>
                <label style={{ color: '#f0f0f0', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="partial_dependencies"
                    value="no"
                    checked={answers.partial_dependencies === 'no'}
                    onChange={(e) => updateAnswer('partial_dependencies', e.target.value)}
                    style={{ marginRight: '8px' }}
                  />
                  No
                </label>
              </div>
              {answers.partial_dependencies === 'yes' && (
                <textarea
                  placeholder="Please describe the dependencies..."
                  value={answers.partial_dependencies_details || ''}
                  onChange={(e) => updateAnswer('partial_dependencies_details', e.target.value)}
                  rows={3}
                  style={{
                    marginTop: '10px',
                    width: '100%',
                    padding: '8px',
                    border: '1.5px solid #9370db',
                    borderRadius: '5px',
                    background: 'rgba(30, 0, 51, 0.5)',
                    color: '#f0f0f0',
                  }}
                />
              )}
            </div>

            {/* Question 3: Transitive Dependencies */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ color: '#f0f0f0', fontWeight: 'bold', display: 'block', marginBottom: '10px' }}>
                3. Are there columns that depend on other non-key columns?
              </label>
              <p style={{ color: '#999', fontSize: '0.9em', marginBottom: '10px' }}>
                (e.g., customer_name depends on customer_id, which is not the primary key)
              </p>
              <div style={{ display: 'flex', gap: '15px' }}>
                <label style={{ color: '#f0f0f0', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="transitive_dependencies"
                    value="yes"
                    checked={answers.transitive_dependencies === 'yes'}
                    onChange={(e) => updateAnswer('transitive_dependencies', e.target.value)}
                    style={{ marginRight: '8px' }}
                  />
                  Yes
                </label>
                <label style={{ color: '#f0f0f0', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="transitive_dependencies"
                    value="no"
                    checked={answers.transitive_dependencies === 'no'}
                    onChange={(e) => updateAnswer('transitive_dependencies', e.target.value)}
                    style={{ marginRight: '8px' }}
                  />
                  No
                </label>
              </div>
              {answers.transitive_dependencies === 'yes' && (
                <textarea
                  placeholder="Please describe the dependencies..."
                  value={answers.transitive_dependencies_details || ''}
                  onChange={(e) => updateAnswer('transitive_dependencies_details', e.target.value)}
                  rows={3}
                  style={{
                    marginTop: '10px',
                    width: '100%',
                    padding: '8px',
                    border: '1.5px solid #9370db',
                    borderRadius: '5px',
                    background: 'rgba(30, 0, 51, 0.5)',
                    color: '#f0f0f0',
                  }}
                />
              )}
            </div>

            {/* Question 4: Candidate Keys */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ color: '#f0f0f0', fontWeight: 'bold', display: 'block', marginBottom: '10px' }}>
                4. Can you identify all candidate keys (potential primary keys) in your tables?
              </label>
              <p style={{ color: '#999', fontSize: '0.9em', marginBottom: '10px' }}>
                (Needed for BCNF - keys that could uniquely identify rows)
              </p>
              <textarea
                placeholder="List candidate keys for each table..."
                value={answers.candidate_keys || ''}
                onChange={(e) => updateAnswer('candidate_keys', e.target.value)}
                rows={4}
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1.5px solid #9370db',
                  borderRadius: '5px',
                  background: 'rgba(30, 0, 51, 0.5)',
                  color: '#f0f0f0',
                }}
              />
            </div>
          </div>

          <button
            onClick={handleNormalize}
            disabled={loading}
            style={{
              padding: '12px 30px',
              background: loading ? '#6c757d' : '#9370db',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '16px',
              fontWeight: 'bold',
              marginRight: '10px',
            }}
          >
            {loading ? 'Normalizing...' : 'Normalize Database'}
          </button>
          <button
            onClick={() => setStep(2)}
            disabled={loading}
            style={{
              padding: '12px 30px',
              background: '#6c757d',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '16px',
            }}
          >
            Back
          </button>
        </div>
      )}

      {step === 4 && result && (
        <div>
          <h4 style={{ color: '#f0f0f0', marginBottom: '20px' }}>✅ Normalization Complete!</h4>
          
          <div style={{ background: '#e8f5e9', padding: '20px', borderRadius: '10px', marginBottom: '20px', color: '#1b5e20' }}>
            <h5 style={{ marginTop: 0 }}>Backup Created</h5>
            <p>
              <strong>Backup Database:</strong> {result.backup_database}
            </p>
            <p style={{ fontSize: '0.9em', marginTop: '10px' }}>
              ⚠️ Your original database has been preserved. You can access it from the databases list.
            </p>
          </div>

          {result.changes && result.changes.length > 0 && (
            <div style={{ background: 'rgba(147, 112, 219, 0.1)', padding: '20px', borderRadius: '10px', marginBottom: '20px' }}>
              <h5 style={{ color: '#f0f0f0' }}>Changes Made:</h5>
              <ul style={{ color: '#ccc' }}>
                {result.changes.map((change, idx) => (
                  <li key={idx} style={{ marginBottom: '8px' }}>{change}</li>
                ))}
              </ul>
            </div>
          )}

          {result.new_tables && result.new_tables.length > 0 && (
            <div style={{ background: 'rgba(147, 112, 219, 0.1)', padding: '20px', borderRadius: '10px', marginBottom: '20px' }}>
              <h5 style={{ color: '#f0f0f0' }}>New Tables Created:</h5>
              <ul style={{ color: '#ccc' }}>
                {result.new_tables.map((table, idx) => (
                  <li key={idx} style={{ marginBottom: '8px' }}>
                    <strong>{table.name}</strong>
                    {table.columns && (
                      <span style={{ color: '#999', fontSize: '0.9em' }}>
                        {' '}({table.columns.join(', ')})
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <button
            onClick={() => {
              setStep(1);
              setNormalForm('');
              setAnalysis(null);
              setAnswers({});
              setResult(null);
              setError('');
              setMessage('');
            }}
            style={{
              padding: '12px 30px',
              background: '#9370db',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer',
              fontSize: '16px',
              fontWeight: 'bold',
            }}
          >
            Start New Normalization
          </button>
        </div>
      )}
    </div>
  );
}

export default NormalizationWizard;