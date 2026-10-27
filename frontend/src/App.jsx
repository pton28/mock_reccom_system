import { useEffect, useState } from 'react';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { ShoppingBag, ArrowUpRight, Sparkles, ChevronDown, X, Search } from 'lucide-react';
import { api } from './services/api';
import { identify, track, cloudTracking } from './services/posthog';
import DataTrace from './pages/DataTrace';
import Home from './pages/Home';
import ProductList from './pages/ProductList';
import ProductDetail from './pages/ProductDetail';
import Cart from './pages/Cart';

const emptyFeed = { items: [], listId: null };
function readSession(id) {
  try { return JSON.parse(sessionStorage.getItem(`nutee-product-demo-v1:${id}`)) || { cart: [], wishlist: [] }; }
  catch { return { cart: [], wishlist: [] }; }
}
export default function App() {
  const [users, setUsers] = useState([]);
  const [user, setUser] = useState(null);
  const [bag, setBag] = useState({ cart: [], wishlist: [] });
  const [feed, setFeed] = useState(emptyFeed);
  const [stats, setStats] = useState({});
  const [revision, setRevision] = useState(0);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const location = useLocation();
  useEffect(() => { window.scrollTo(0, 0); }, [location.pathname]);
  useEffect(() => {
    api('/users').then(result => {
      if (!result.length) throw new Error('No demo users. Run python -m scripts.demo first.');
      setUsers(result); setUser(result[0]); setBag(readSession(result[0].id)); identify(result[0].id);
    }).catch(e => setError(e.message));
  }, []);
  useEffect(() => {
    if (!user) return;
    let active = true;
    setFeed(emptyFeed);
    Promise.allSettled([api('/products?limit=16'), api('/analytics/status')]).then(([catalog, status]) => {
      if (!active) return;
      setFeed({ items: catalog.status === 'fulfilled' ? catalog.value.items : [], listId: crypto.randomUUID() });
      if (status.status === 'fulfilled') setStats(status.value);
      if (catalog.status === 'rejected') setError('Products could not load. Please try again.');
    });
    return () => { active = false; };
  }, [user?.id, revision]);
  useEffect(() => {
    if (user) sessionStorage.setItem(`nutee-product-demo-v1:${user.id}`, JSON.stringify(bag));
  }, [bag, user?.id]);
  useEffect(() => { if (notice) { const timer = setTimeout(() => setNotice(''), 3500); return () => clearTimeout(timer); } }, [notice]);
  function switchUser(id) {
    const next = users.find(u => u.id === id);
    setFeed(emptyFeed); setUser(next); setBag(readSession(id)); identify(id);
  }
  function capture(name, props) { return track(user.id, name, props).catch(e => setError(`Tracking: ${e.message}`)); }
  const shop = {
    user, ...bag, revision, track: capture, setCheckoutBusy,
    add(p) {
      if (bag.cart.some(x => x.id === p.id)) return;
      setBag(previous => ({ ...previous, cart: [...previous.cart, p] }));
      capture('add_to_cart', { product_id: p.id }); setNotice('A good choice. Added to your bag.');
    },
    save(p) {
      const saved = bag.wishlist.includes(p.id);
      setBag(previous => ({ ...previous, wishlist: saved ? previous.wishlist.filter(id => id !== p.id) : [...previous.wishlist, p.id] }));
      if (!saved) capture('add_to_wishlist', { product_id: p.id });
      setNotice(saved ? 'Removed from saved products.' : 'Saved for your next visit.');
    },
    remove(id) { setBag(previous => ({ ...previous, cart: previous.cart.filter(p => p.id !== id) })); capture('remove_from_cart', { product_id: id }); },
    clearCart() { setBag(previous => ({ ...previous, cart: [] })); },
    refresh() { setRevision(r => r + 1); },
  };
  return <><div className="announcement">A new kind of connection. Tech, tailored to you. <Sparkles size={12}/><span>SYNTHETIC STORE / REAL DISCOVERY</span></div>
    <header><div className="nav-shell"><Link to="/" className="logo">nutee<span>✳</span></Link><nav aria-label="Main navigation"><NavLink to="/" end>Discover</NavLink><NavLink to="/products">Shop all</NavLink><NavLink to="/data-trace">Data trace</NavLink></nav><div className="nav-actions"><Link to="/products" className="icon-button search-nav" aria-label="Search"><Search size={20}/></Link><Link to="/cart" className="bag-link" aria-label={`Shopping bag, ${bag.cart.length} products`}><ShoppingBag size={20}/><span>{bag.cart.length}</span></Link><div className="user-picker"><span className="avatar">{user?.name?.[0] || '?'}</span><select disabled={checkoutBusy} aria-label="Switch demo user" value={user?.id || ''} onChange={e => switchUser(e.target.value)}>{users.map(u => <option value={u.id} key={u.id}>{u.id}</option>)}</select><ChevronDown size={13}/></div></div></div></header>
    <main>{error && <div className="error global-error" role="alert">{error}<button className="icon-button" onClick={() => setError('')} aria-label="Dismiss error"><X size={16}/></button></div>}{!user ? <div className="empty"><h1>Welcome to NUTEE.</h1><p>{error ? 'The store could not load. Check the API connection and demo data.' : 'Getting your discoveries ready…'}</p></div> : <Routes><Route path="/data-trace" element={<DataTrace/>}/><Route path="/" element={<Home shop={shop} feed={feed}/>}/><Route path="/products" element={<ProductList shop={shop}/>}/><Route path="/products/:id" element={<ProductDetail shop={shop}/>}/><Route path="/cart" element={<Cart key={user.id} shop={shop}/>}/><Route path="*" element={<div className="empty"><h1>That page wandered off.</h1><Link to="/">Back to discoveries</Link></div>}/></Routes>}</main>
    <footer><div className="footer-top"><Link to="/" className="logo">nutee<span>✳</span></Link><p>Good tech finds its people.</p><Link to="/products">Explore the collection <ArrowUpRight size={17}/></Link></div><div className="footer-bottom"><span>© {new Date().getFullYear()} NUTEE · A demo storefront</span><span className="tracking-status"><i/>{cloudTracking ? 'PostHog test project connected' : 'Local demo mode'} · {stats.products || 0} products</span></div></footer>{notice && <div className="toast" role="status"><Sparkles size={16}/>{notice}</div>}</>;
}
