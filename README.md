MultiAlchemy
==

[![Build Status](https://travis-ci.org/mwhite/MultiAlchemy.png)](https://travis-ci.org/mwhite/MultiAlchemy)
[![Coverage Status](https://coveralls.io/repos/mwhite/MultiAlchemy/badge.png)](https://coveralls.io/r/mwhite/MultiAlchemy)
[![Dependency Status](https://gemnasium.com/mwhite/MultiAlchemy.png)](https://gemnasium.com/mwhite/MultiAlchemy)

MultiAlchemy is an experimental [SQLAlchemy](http://www.sqlalchemy.org)
extension that makes it easy to write row-based multi-tenant applications
without having to manually ensure data separation for every operation.

Usage
--

Here's an example schema, taken from the tests, that has a tenant table, one
other global table (users), and one per-tenant table (posts).

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

If we do a query involving a multitenant model, a filter will automatically be
added to limit the results to only those matching the current session's tenant.

```python
>>> print(str(session.query(Post)))
SELECT posts.id AS posts_id, posts.title AS posts_title, posts.author_id AS posts_author_id, posts.tenant_id AS posts_tenant_id 
FROM posts 
WHERE posts.tenant_id = :tenant_id_1
```

This works for joins too.

```python
>>> print(str(session.query(User).join(Post)))
SELECT users.id AS users_id, users.name AS users_name 
FROM users JOIN posts ON users.id = posts.author_id 
WHERE posts.tenant_id = :tenant_id_1
```

You can bypass the tenant checking by passing `safe=False` to `session.query()`.

Instances also automatically get assigned the correct `tenant_id` when you add
them to the session:

```python
>>> post = Post(title='Baz', author_id=1)
>>> session.add(post)
>>> post.tenant_id
1
```

License
--

Copyright 2014 Michael White

Released under the MIT License.  See LICENSE.txt.
