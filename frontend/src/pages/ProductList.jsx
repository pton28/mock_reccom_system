import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search } from 'lucide-react';
import { api } from '../services/api';
import ProductCard from '../components/ProductCard';

export default function ProductList({ shop }) {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get('q') || '');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true; setData(null); setError('');
    api(`/products?${params}&limit=300`).then(result => { if (active) setData({ ...result, listId: crypto.randomUUID() }); }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [params.toString(), shop.revision]);
  function search(e) { e.preventDefault(); setParams({ ...Object.fromEntries(params), q: query }); if (query.trim()) shop.track('search', { query, page: 'search' }); }
  return <section className="section page-section"><span className="eyebrow green">THE COLLECTION</span><h1>Find your everyday upgrade.</h1><div className="catalog-tools"><form className="search-box" onSubmit={search}><Search size={18}/><input aria-label="Search products" placeholder="Search by product, category, or brand" value={query} onChange={e => setQuery(e.target.value)} maxLength={200}/><button>Search</button></form><select aria-label="Filter category" value={params.get('category') || ''} onChange={e => setParams({ ...Object.fromEntries(params), category: e.target.value })}><option value="">All categories</option>{(data?.categories || []).map(c => <option key={c} value={c}>{c}</option>)}</select></div>
    {error && <p role="alert" className="error">{error}</p>}{!data && !error && <p className="empty">Loading the collection…</p>}
    {data && <><p className="results-count">{data.total} considered choices</p><div className="product-grid">{data.items.map((p, i) => <ProductCard key={p.id} product={p} shop={shop} index={i} page={params.get('q') ? 'search' : 'catalog'} listId={data.listId}/>)}</div>{!data.total && <p className="empty">No matches yet. Try another product or category.</p>}</>}
  </section>;
}
