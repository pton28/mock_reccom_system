import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Heart, ShoppingBag } from 'lucide-react';
import { api } from '../services/api';
import { ProductArt, money } from '../components/ProductCard';

export default function ProductDetail({ shop }) {
  const { id } = useParams();
  const [product, setProduct] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true; setProduct(null); setError('');
    api(`/products/${id}`).then(async p => {
      if (!active) return;
      setProduct(p);
      await shop.track('product_view', { product_id: p.id });
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [id, shop.user.id, shop.revision]);
  if (error) return <p className="empty error" role="alert">{error}</p>;
  if (!product) return <p className="empty">Finding your next favorite…</p>;
  return <section className="page-section"><Link className="text-link" to="/products"><ArrowLeft size={16}/> Back to collection</Link><div className="detail"><ProductArt product={product} large/><div className="detail-copy"><span className="eyebrow green">{product.category} / {product.brand}</span><h1>{product.name}</h1><p>{product.description}</p><h2>{money(product.price)}</h2><p>{product.stock} available · Synthetic product · No real payment</p><div className="actions"><button className="button dark" disabled={!product.stock || shop.cart.some(p => p.id === id)} onClick={() => shop.add(product)}><ShoppingBag size={18}/>{shop.cart.some(p => p.id === id) ? 'In your bag' : 'Add to bag'}</button><button className="button outline" onClick={() => shop.save(product)}><Heart size={17}/>{shop.wishlist.includes(id) ? 'Saved' : 'Save for later'}</button></div><dl>{Object.entries(product.attributes).map(([k, v]) => <div key={k}><dt>{k.replaceAll('_', ' ')}</dt><dd>{String(v)}</dd></div>)}</dl></div></div></section>;
}
