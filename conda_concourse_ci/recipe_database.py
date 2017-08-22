import os

from sqlalchemy import create_engine, _and
from sqlalchemy.orm import sessionmaker

from .model import Recipe, BuildDependency, RunDependency, Output


def _get_build_dep_records(metadata, session):
    deps = (metadata.meta.get('requirements', {}).get('build', []) +
            metadata.meta.get('requirements', {}).get('host', []))
    records = []
    # TODO: is this faster as an OR query to the DB?
    for dep in deps:
        name, constraint = dep.split(' ', 1)
        record = session.query(BuildDependency).filter(_and(BuildDependency.name == name,
                                                    BuildDependency.constraint == constraint))\
                                  .one_or_none()
        if not record:
            record = BuildDependency(name=name, constraint=constraint)
            session.add(record)
        records.append(record)
    session.commit()
    return records


def _get_run_dep_records(metadata, session):
    deps = (metadata.meta.get('requirements', {}).get('run', []) +
            metadata.meta.get('test', {}).get('requires', []))
    records = []
    # TODO: is this faster as an OR query to the DB?
    for dep in deps:
        name, constraint = dep.split(' ', 1)
        record = session.query(RunDependency)\
                        .filter(_and(RunDependency.name == name,
                                     RunDependency.constraint == constraint))\
                        .one_or_none()
        if not record:
            record = RunDependency(name=name, constraint=constraint)
            session.add(record)
        records.append(record)
    session.commit()
    return records


def _get_output_records(metadata, session):
    outputs = metadata.meta.get('outputs', [])
    records = []
    # TODO: is this faster as an OR query to the DB?
    for output in outputs:
        name = output.get('name', metadata.name())
        version = output.get('version', metadata.version())
        record = session.query(Output)\
                        .filter(_and(Output.name == name,
                                     Output.version == version))\
                        .one_or_none()
        if not record:
            record = Output(name=name, version=version)
            session.add(record)
        records.append(record)
    session.commit()
    return records


def _create_or_update_record(metadata, session, root_path):
    record = session.query(Recipe)\
                    .filter(_and(Recipe.name == metadata.name(),
                                 Recipe.version == metadata.version(),
                                 Recipe.build_string == metadata.build_id()))\
                    .one_or_none()
    repo, branch, commit_id = get_git_info(metadata.path)
    if not record:
        record = Recipe(name=metadata.name(),
                        version=metadata.version(),
                        build_string=metadata.build_id(),
        )
        session.add(record)
    # Store path relative to root of aggregate, so that it works on
    #    many computers
    record.path = metadata.path.replace(root_path + os.path.sep, ''),
    record.origin_repo = repo
    record.origin_branch = branch
    record.commit_id = commit_id
    record.build_deps = _get_build_dep_records(metadata, session)
    record.run_deps = _get_run_dep_records(metadata, session)
    record.outputs = _get_output_records(metadata, session)

    # associate build deps with DB entries
    session.commit()


def populate(metadata_objects, db_filename):
    if not os.path.isabs(db_filename):
        db_filename = os.path.join(os.getcwd(), db_filename)
    engine = create_engine('sqlite:///' + db_filename, echo=True)
    session = sessionmaker(bind=engine)()
    for metadata in metadata_objects:
        _create_or_update_record(metadata, session)
