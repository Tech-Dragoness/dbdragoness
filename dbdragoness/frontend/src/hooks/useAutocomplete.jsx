import { useState, useRef, useCallback } from 'react';
import axios from 'axios';

export function useAutocomplete() {
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [currentFullQuery, setCurrentFullQuery] = useState('');
  const autocompleteTimeout = useRef(null);

  const fetchSuggestions = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    try {
      const response = await axios.post('/api/autocomplete/history', {
        query,
        limit: 5
      });

      if (response.data.success && response.data.suggestions.length > 0) {
        setSuggestions(response.data.suggestions);
        setShowSuggestions(true);
        setSelectedIndex(-1);
      } else {
        setSuggestions([]);
        setShowSuggestions(false);
      }
    } catch (err) {
      console.error('Autocomplete error:', err);
      setSuggestions([]);
      setShowSuggestions(false);
    }
  }, []);

  /**
   * Extract the position where the current command starts (after last semicolon)
   */
  const getCurrentCommandStart = useCallback((fullQuery) => {
    const lastSemicolon = fullQuery.lastIndexOf(';');
    return lastSemicolon === -1 ? 0 : lastSemicolon + 1;
  }, []);

  /**
   * Apply a suggestion by replacing ONLY the current command (after last semicolon)
   * while preserving whitespace including newlines
   * 
   * Example:
   * Input: "use db1;\nselect * from"
   * Suggestion: "select * from orders"
   * Result: "use db1;\nselect * from orders"
   */
  const applySuggestion = useCallback((fullQuery, suggestion) => {
    const lastSemicolon = fullQuery.lastIndexOf(';');
    
    if (lastSemicolon === -1) {
      // No semicolon found, replace entire query
      return suggestion;
    }
    
    // Keep everything up to and including the semicolon, plus any whitespace after it
    const beforeSemicolon = fullQuery.substring(0, lastSemicolon + 1);
    const afterSemicolon = fullQuery.substring(lastSemicolon + 1);
    
    // Extract any leading whitespace (including newlines) from what comes after the semicolon
    const whitespaceMatch = afterSemicolon.match(/^(\s*)/);
    const leadingWhitespace = whitespaceMatch ? whitespaceMatch[1] : '';
    
    // Reconstruct: previous commands + semicolon + whitespace + new suggestion
    const newQuery = beforeSemicolon + leadingWhitespace + suggestion;
    
    return newQuery;
  }, []);

  const handleQueryChange = useCallback((newQuery, callback) => {
    // Clear previous timeout
    if (autocompleteTimeout.current) {
      clearTimeout(autocompleteTimeout.current);
    }

    // Store the current query for later use when applying suggestions
    setCurrentFullQuery(newQuery);

    // Call the callback immediately (update state)
    callback(newQuery);

    // Debounce autocomplete fetch
    autocompleteTimeout.current = setTimeout(() => {
      fetchSuggestions(newQuery);
    }, 300);
  }, [fetchSuggestions]);

  const handleKeyDown = useCallback((e, currentQuery, onSelect) => {
    if (!showSuggestions || suggestions.length === 0) return false;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => 
          prev < suggestions.length - 1 ? prev + 1 : prev
        );
        return true;

      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => prev > 0 ? prev - 1 : -1);
        return true;

      case 'Enter':
        if (selectedIndex >= 0) {
          e.preventDefault();
          // Apply suggestion by replacing only current command
          const newQuery = applySuggestion(currentQuery, suggestions[selectedIndex]);
          onSelect(newQuery);
          setShowSuggestions(false);
          setSelectedIndex(-1);
          return true;
        }
        break;

      case 'Escape':
        setShowSuggestions(false);
        setSelectedIndex(-1);
        return true;

      case 'Tab':
        if (selectedIndex >= 0) {
          e.preventDefault();
          // Apply suggestion by replacing only current command
          const newQuery = applySuggestion(currentQuery, suggestions[selectedIndex]);
          onSelect(newQuery);
          setShowSuggestions(false);
          setSelectedIndex(-1);
          return true;
        }
        break;
    }

    return false;
  }, [showSuggestions, suggestions, selectedIndex, applySuggestion]);

  const selectSuggestion = useCallback((suggestion, onSelect) => {
    // Apply suggestion by replacing only current command
    const newQuery = applySuggestion(currentFullQuery, suggestion);
    onSelect(newQuery);
    setShowSuggestions(false);
    setSelectedIndex(-1);
  }, [currentFullQuery, applySuggestion]);

  const hideSuggestions = useCallback(() => {
    setShowSuggestions(false);
    setSelectedIndex(-1);
  }, []);

  return {
    suggestions,
    showSuggestions,
    selectedIndex,
    handleQueryChange,
    handleKeyDown,
    selectSuggestion,
    hideSuggestions
  };
}