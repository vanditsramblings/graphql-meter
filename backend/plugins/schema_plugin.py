"""Schema plugin — GraphQL AST parsing, operation extraction, test data generation."""

import re
from typing import List, Dict, Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel

from backend.core.plugin_base import PluginBase

try:
    from graphql import parse as gql_parse, print_ast
    from graphql.language import ast as gql_ast
    HAS_GRAPHQL_CORE = True
except ImportError:
    HAS_GRAPHQL_CORE = False


# Smart defaults for common field names
_SMART_DEFAULTS = {
    "id": "test-{r}",
    "customerid": "test-customer-{r}",
    "orderid": "test-order-{r}",
    "productid": "test-product-{r}",
    "userid": "test-user-{r}",
    "email": "test{r}@example.com",
    "firstname": "TestFirst",
    "lastname": "TestLast",
    "name": "Test Name {r}",
    "phone": "555-0{r}",
    "street": "123 Test St",
    "city": "Testville",
    "state": "CA",
    "zipcode": "90210",
    "country": "US",
    "quantity": 1,
    "limit": 10,
    "page": 1,
    "query": "test",
    "message": "test-{r}",
    "messageinteger": "{r}",
    "messagedouble": "{r}.5",
    "messageuuid": "uuid-{r}",
    "messagetime": "2026-01-01T00:{r}:00Z",
    "category": "general",
    "status": "ACTIVE",
    "label": "item-{r}",
    "count": "{r}",
    "score": "{r}.99",
    "referenceid": "ref-{r}",
    "scheduledat": "2026-01-01T{r}:00:00Z",
    "active": True,
}

_TYPE_DEFAULTS = {
    "String": '""',
    "Int": 0,
    "Float": 0.0,
    "Boolean": False,
    "ID": "test-{r}",
}


def _resolve_named_type(type_node) -> Optional[str]:
    """Recursively unwrap NonNull/List wrappers to get the named type."""
    if type_node is None:
        return None
    if isinstance(type_node, gql_ast.NamedTypeNode):
        return type_node.name.value
    if isinstance(type_node, (gql_ast.NonNullTypeNode, gql_ast.ListTypeNode)):
        return _resolve_named_type(type_node.type)
    return None


def _is_required(type_node) -> bool:
    return isinstance(type_node, gql_ast.NonNullTypeNode)


def _is_list(type_node) -> bool:
    if isinstance(type_node, gql_ast.NonNullTypeNode):
        return _is_list(type_node.type)
    return isinstance(type_node, gql_ast.ListTypeNode)


def _extract_operations_ast(schema_text: str) -> Dict[str, Any]:
    """Parse schema with graphql-core and extract operations."""
    doc = gql_parse(schema_text)

    input_types = {}
    operations = []

    # First pass: collect input types
    for defn in doc.definitions:
        if isinstance(defn, gql_ast.InputObjectTypeDefinitionNode):
            fields = []
            for f in (defn.fields or []):
                type_name = _resolve_named_type(f.type)
                fields.append({
                    "name": f.name.value,
                    "type": type_name or "String",
                    "required": _is_required(f.type),
                    "is_list": _is_list(f.type),
                })
            input_types[defn.name.value] = fields

    # Second pass: extract queries/mutations
    for defn in doc.definitions:
        if isinstance(defn, gql_ast.ObjectTypeDefinitionNode):
            op_type = None
            if defn.name.value == "Query":
                op_type = "query"
            elif defn.name.value == "Mutation":
                op_type = "mutation"

            if op_type and defn.fields:
                for field in defn.fields:
                    variables = []
                    for arg in (field.arguments or []):
                        type_name = _resolve_named_type(arg.type)
                        variables.append({
                            "name": arg.name.value,
                            "type": type_name or "String",
                            "required": _is_required(arg.type),
                            "is_list": _is_list(arg.type),
                            "is_input_type": type_name in input_types if type_name else False,
                        })
                    operations.append({
                        "name": field.name.value,
                        "type": op_type,
                        "variables": variables,
                    })

    return {"operations": operations, "input_types": input_types}


def _extract_operations_regex(schema_text: str) -> Dict[str, Any]:
    """Fallback regex-based parser."""
    operations = []
    block_re = re.compile(r'type\s+(Query|Mutation)\s*\{([^}]+)\}', re.DOTALL)
    field_re = re.compile(r'(\w+)\s*\(([^)]*)\)\s*:\s*(\S+)')
    arg_re = re.compile(r'(\w+)\s*:\s*(\[?\w+!?\]?!?)')

    for m in block_re.finditer(schema_text):
        op_type = "query" if m.group(1) == "Query" else "mutation"
        body = m.group(2)
        for fm in field_re.finditer(body):
            vars_ = []
            for am in arg_re.finditer(fm.group(2)):
                raw = am.group(2)
                required = raw.endswith("!")
                is_list = raw.startswith("[")
                clean = raw.strip("[]!")
                vars_.append({
                    "name": am.group(1),
                    "type": clean,
                    "required": required,
                    "is_list": is_list,
                    "is_input_type": clean.endswith("Input"),
                })
            operations.append({"name": fm.group(1), "type": op_type, "variables": vars_})

    return {"operations": operations, "input_types": {}}


def _generate_default_value(var_name: str, var_type: str, is_input: bool, input_types: dict) -> Any:
    """Generate a smart default value for a variable."""
    lower = var_name.lower()
    for key, val in _SMART_DEFAULTS.items():
        if key in lower:
            return val

    if is_input and var_type in input_types:
        obj = {}
        for f in input_types[var_type]:
            obj[f["name"]] = _generate_default_value(f["name"], f["type"], f["type"] in input_types, input_types)
        return obj

    return _TYPE_DEFAULTS.get(var_type, "")


def _build_query_string(op_name: str, op_type: str, variables: list) -> str:
    """Build a GraphQL query string for an operation."""
    var_defs = []
    args = []
    for v in variables:
        t = v["type"]
        if v.get("is_input_type"):
            t = v["type"]
        if v.get("is_list"):
            t = f"[{t}]"
        if v.get("required"):
            t += "!"
        var_defs.append(f"${v['name']}: {t}")
        args.append(f"{v['name']}: ${v['name']}")

    var_str = f"({', '.join(var_defs)})" if var_defs else ""
    arg_str = f"({', '.join(args)})" if args else ""
    keyword = op_type

    return f"{keyword} {op_name}{var_str} {{\n  {op_name}{arg_str} {{\n    __typename\n  }}\n}}"


class ParseRequest(BaseModel):
    schema_text: str


class GenerateTestDataRequest(BaseModel):
    variable_name: str
    variable_type: str
    is_input_type: bool = False
    input_types: dict = {}


class SchemaPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "schema"

    @property
    def description(self) -> str:
        return "GraphQL schema parsing (AST + regex fallback), test data generation"

    def _register_routes(self):
        @self.router.post("/parse")
        async def parse_schema(body: ParseRequest):
            schema_text = body.schema_text.strip()
            if not schema_text:
                raise HTTPException(400, "Schema text is required")

            result = None
            parse_method = "ast"

            if HAS_GRAPHQL_CORE:
                try:
                    result = _extract_operations_ast(schema_text)
                except Exception as e:
                    parse_method = "regex"
                    result = _extract_operations_regex(schema_text)
            else:
                parse_method = "regex"
                result = _extract_operations_regex(schema_text)

            if not result["operations"]:
                raise HTTPException(400, "No operations found in schema")

            # Enrich with query strings and default test data
            for op in result["operations"]:
                op["query"] = _build_query_string(op["name"], op["type"], op["variables"])
                for v in op["variables"]:
                    v["default_value"] = _generate_default_value(
                        v["name"], v["type"],
                        v.get("is_input_type", False),
                        result.get("input_types", {}),
                    )

            return {
                "operations": result["operations"],
                "input_types": result.get("input_types", {}),
                "parse_method": parse_method,
                "operation_count": len(result["operations"]),
            }

        @self.router.post("/generate-test-data")
        async def generate_test_data(body: GenerateTestDataRequest):
            val = _generate_default_value(
                body.variable_name, body.variable_type,
                body.is_input_type, body.input_types,
            )
            return {"variable_name": body.variable_name, "value": val}
