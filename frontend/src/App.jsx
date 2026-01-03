import React from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Home from './pages/Home'
import DatabaseDetails from './pages/DatabaseDetails'
import TableDetails from './pages/TableDetails'
import CollectionDetails from './pages/CollectionDetails'
import TriggersList from './pages/TriggersList';
import ProceduresList from './pages/ProceduresList';
import GlobalQuery from './pages/GlobalQuery';
import UsersManagement from './pages/UsersManagement';
import CredentialsPage from './pages/CredentialsPage';

function App() {
  return (
    <Router basename="/react">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/db/:dbName" element={<DatabaseDetails />} />
        <Route path="/db/:dbName/table/:tableName" element={<TableDetails />} />
        <Route path="/db/:dbName/collection/:collectionName" element={<CollectionDetails />} />
        <Route path="*" element={<Navigate to="/" replace />} />
        <Route path="/db/:dbName/triggers" element={<TriggersList />} />
        <Route path="/db/:dbName/procedures" element={<ProceduresList />} />
        <Route path="/query" element={<GlobalQuery />} />
        <Route path="/db/:dbName/users" element={<UsersManagement />} />
        <Route path="/credentials/:handlerName" element={<CredentialsPage />} />
      </Routes>
    </Router>
  )
}

export default App