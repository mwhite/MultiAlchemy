MultiAlchemy
==

MultiAlchemy is an experimental SQLAlchemy extension that makes it easy to
develop multi-tenant applications without having to worry about keeping each
tenant's data separate in every operation.

At the moment, it only works on SQLAlchemy 0.9, it relies on monkey-patching
implementation details of the SQLAlchemy ORM, it's probably is a leaky
abstraction in unknown ways, and it lacks decent configuration options, so use
at your own risk!

Background
-- 

A multi-tenant application is one that handles many different users' or tenants'
data, each of which is mostly or completely separate from the rest.

One solution for storing multi-tenant data in a RDBMS would be to create a
separate database for each tenant.  This doesn't scale for large numbers of
tenants.  Creating a database can be an expensive operation, schema migrations
become more difficult, and there's no ability to have part of the data be shared
between tenants.

Another solution is to use
[schemas](http://www.postgresql.org/docs/9.3/static/ddl-schemas.html), but this
has the same essential properties as separate databases.

The most scalable solution is to have a `tenant_id` foreign key in each table
that's part of the multi-tenant data.  However, it's a pain and a potential
security risk for developers to pass around the current session's tenant and
ensure it gets added to any new objects created with the ORM and added as a
condition in any queries.

MultiAlchemy aims to automate this, abstracting the multi-tenancy out of the
model definitions and queries.

Usage
--

Here's an example schema taken from the tests that has a tenant table, one other
global table (users), and one per-tenant table (posts).

```python
from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import multialchemy

engine = create_engine("sqlite:///multi_blog.db")
Base = declarative_base(cls=multialchemy.Base)

@Base.tenant_class
class Tenant(Base):
    __tablename__ = 'tenants'
    __multitenant__ = False
    id = Column(Integer, primary_key=True)
    name = Column(String(200))

class User(Base):
    __tablename__ = 'users'
    __multitenant__ = False
    id = Column(Integer, primary_key=True)
    name = Column(String(200))

class Post(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    author_id = Column(Integer, ForeignKey('users.id'))
    author = relationship(User, backref='posts')
```

If we look at the SQL emitted when creating these tables, we see that a
`tenant_id` foreign key was added automatically.

```sql
CREATE TABLE posts (
	id INTEGER NOT NULL, 
	title VARCHAR(200), 
	author_id INTEGER, 
	tenant_id INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(author_id) REFERENCES users (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);
```

Now let's create a multitenant-enabled session:

```python
>>> TenantSession = sessionmaker(bind=engine, class_=multialchemy.TenantSession)
>>> session = TenantSession()
```

Then we can find a tenant using an unsafe query that bypasses tenant checking, and
bind it as the current session's tenant.

```python
>>> tenant = session.query(Tenant, safe=False).first()
>>> session.tenant = tenant
```

If we do a query involving a multitenant model, a criterion will automatically
be added to filter the results to only those matching the current session's
tenant, even for joins.

```python
>>> print(str(session.query(Post)))
SELECT posts.id AS posts_id, posts.title AS posts_title, posts.author_id AS posts_author_id, posts.tenant_id AS posts_tenant_id 
FROM posts 
WHERE posts.tenant_id = :tenant_id_1
>>> print(str(session.query(models.User).join(models.User.posts)))
```

You can bypass the tenant checking by passing `safe=False` to `session.query()`.
