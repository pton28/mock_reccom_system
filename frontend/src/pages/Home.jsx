import { Link } from 'react-router-dom';
import { ArrowRight, Sparkles, Headphones, ShieldCheck, Truck, RefreshCw } from 'lucide-react';
import ProductCard from '../components/ProductCard';

export default function Home({ shop, feed }) {
  return <>
    <section className="hero"><div className="hero-copy"><span className="eyebrow"><span/>A little more you.</span><h1>Good tech.<br/>Great chemistry.</h1><p>A world of possibilities, curated around you.<br/>Discover your next everyday favorite.</p><Link className="button light" to="/products">Find your next thing <ArrowRight size={18}/></Link><div className="hero-foot"><span className="mini-avatars">● ● ●</span><span>Made for every kind of curious.</span></div></div>
      <div className="hero-art"><div className="hero-ring one"/><div className="hero-ring two"/><span className="floating-note"><Sparkles size={14}/> Your kind of sound</span><Headphones className="hero-headphones" strokeWidth={1.1}/><div className="hero-product"><span>TURN UP THE EVERYDAY</span><strong>A sound decision.</strong><Link to="/products?category=headphones">Explore audio <ArrowRight size={16}/></Link></div><span className="edition">THE DAILY EDIT / 01</span></div>
    </section>
    <div className="benefits"><span><Truck/> Thoughtful tech, delivered</span><span><ShieldCheck/> Two-year demo warranty</span><span><RefreshCw/> Discover. Explore. Repeat.</span><span className="synthetic-label">A synthetic shopping experience</span></div>
    <section className="section home-collection">
      <div className="section-heading"><div><span className="eyebrow green">THE EVERYDAY COLLECTION</span><h2>Find something worth discovering.</h2><p>Everyday essentials and fresh finds, all in one place.</p></div><Link className="text-link" to="/products">Shop all products <ArrowRight size={17}/></Link></div>
      <div className="category-links" aria-label="Browse categories">{[['All products', '/products'], ['Audio', '/products?category=headphones'], ['Laptops', '/products?category=laptops'], ['Phones', '/products?category=phones'], ['Accessories', '/products?category=keyboards']].map(([label, url]) => <Link key={label} to={url}>{label}<ArrowRight size={14}/></Link>)}</div>
      {!feed.listId ? <p role="status">Loading products...</p> : !feed.items.length ? <p>No products available yet. <button className="button" onClick={shop.refresh}>Try again</button></p> : <div className="product-grid">{feed.items.map((p, i) => <ProductCard key={p.id} product={p} shop={shop} index={i} page="home" listId={feed.listId}/>)}</div>}
    </section>
    <section className="explore-banner"><div><span className="eyebrow green">LESS SCROLLING. MORE DISCOVERING.</span><h2>Your interests lead the way.</h2><p>Explore products at your own pace, one discovery at a time.</p></div><Link className="button dark" to="/products">Explore all tech <ArrowRight size={18}/></Link></section>
  </>;
}
