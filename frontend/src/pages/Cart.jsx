import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Trash2 } from 'lucide-react';
import { ProductArt, money } from '../components/ProductCard';
import { post } from '../services/api';
import { captureCloud, getSessionId } from '../services/posthog';

export default function Cart({ shop }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [order, setOrder] = useState(null);
  const pending = useRef(null);
  async function checkout() {
    setBusy(true); shop.setCheckoutBusy(true); setError('');
    const signature = JSON.stringify([shop.user.id, shop.cart.map(p => p.id).sort()]);
    if (pending.current?.signature !== signature) pending.current = { signature, id: crypto.randomUUID() };
    try {
      const result = await post('/checkout', { order_id: pending.current.id, user_id: shop.user.id, product_ids: shop.cart.map(p => p.id), session_id: getSessionId() });
      result.events.forEach(captureCloud); setOrder(result); shop.clearCart(); shop.refresh();
    } catch (e) { setError(e.message); } finally { setBusy(false); shop.setCheckoutBusy(false); }
  }
  return <section className="page-section"><span className="eyebrow green">GOOD CHOICES LIVE HERE</span><h1>Your shopping bag.</h1>{error && <p role="alert" className="error">{error}</p>}{order && <div className="success" role="status">Your demo order is complete. No payment was taken. Order {order.order_id.slice(0, 8)}.</div>}
    {!shop.cart.length ? <div className="empty"><h2>A little room for discovery.</h2><p>Your bag is empty.</p><Link className="button dark" to="/products">Explore the collection <ArrowRight size={16}/></Link></div> : <div className="cart-layout"><div>{shop.cart.map(p => <div className="cart-row" key={p.id}><ProductArt product={p}/><div><Link to={`/products/${p.id}`}>{p.name}</Link><p>{p.category} · 1 unit</p><strong>{money(p.price)}</strong></div><button disabled={busy} className="icon-button" aria-label={`Remove ${p.name}`} onClick={() => shop.remove(p.id)}><Trash2 size={18}/></button></div>)}</div><aside className="order-summary"><h2>The good stuff.</h2><div><span>Subtotal</span><strong>{money(shop.cart.reduce((sum, p) => sum + p.price, 0))}</strong></div><p>Demo checkout only. All products and users are synthetic.</p><button className="button dark" disabled={busy} onClick={checkout}>{busy ? 'Completing order…' : 'Complete demo purchase'}<ArrowRight size={16}/></button></aside></div>}
  </section>;
}
