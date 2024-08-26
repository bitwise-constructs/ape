import re
from typing import Optional

import pytest
from ethpm_types import MethodABI
from ethpm_types.abi import ABIType
from hexbytes import HexBytes

from ape.utils import run_in_tempdir
from ape_ethereum.trace import CallTrace, Trace, TraceApproach, TransactionTrace
from tests.conftest import geth_process_test

LOCAL_TRACE = r"""
Call trace for '0x([A-Fa-f0-9]{64})'
tx\.origin=0x[a-fA-F0-9]{40}
ContractA\.methodWithoutArguments\(\) -> 0x[A-Fa-f0-9]{2,}..[A-Fa-f0-9]{4} \[\d+ gas\]
├── SYMBOL\.supercluster\(x=234444\) -> \[
│       \[23523523235235, 11111111111, 234444\],
│       \[
│         345345347789999991,
│         99999998888882,
│         345457847457457458457457457
│       \],
│       \[234444, 92222229999998888882, 3454\],
│       \[
│         111145345347789999991,
│         333399998888882,
│         234545457847457457458457457457
│       \]
│   \] \[\d+ gas\]
├── SYMBOL\.methodB1\(lolol="ice-cream", dynamo=345457847457457458457457457\) \[\d+ gas\]
│   ├── ContractC\.getSomeList\(\) -> \[
│   │     3425311345134513461345134534531452345,
│   │     111344445534535353,
│   │     993453434534534534534977788884443333
│   │   \] \[\d+ gas\]
│   └── ContractC\.methodC1\(
│         windows95="simpler",
│         jamaica=345457847457457458457457457,
│         cardinal=Contract[A|C]
│       \) \[\d+ gas\]
├── SYMBOL\.callMe\(blue=tx\.origin\) -> tx\.origin \[\d+ gas\]
├── SYMBOL\.methodB2\(trombone=tx\.origin\) \[\d+ gas\]
│   ├── ContractC\.paperwork\(Contract[A|C]\) -> \(
│   │     os="simpler",
│   │     country=345457847457457458457457457,
│   │     wings=Contract[A|C]
│   │   \) \[\d+ gas\]
│   ├── ContractC\.methodC1\(windows95="simpler", jamaica=0, cardinal=Contract[A|C]\) \[\d+ gas\]
│   ├── ContractC\.methodC2\(\) \[\d+ gas\]
│   └── ContractC\.methodC2\(\) \[\d+ gas\]
├── ContractC\.addressToValue\(tx.origin\) -> 0 \[\d+ gas\]
├── SYMBOL\.bandPractice\(tx.origin\) -> 0 \[\d+ gas\]
├── SYMBOL\.methodB1\(lolol="lemondrop", dynamo=0\) \[\d+ gas\]
│   ├── ContractC\.getSomeList\(\) -> \[
│   │     3425311345134513461345134534531452345,
│   │     111344445534535353,
│   │     993453434534534534534977788884443333
│   │   \] \[\d+ gas\]
│   └── ContractC\.methodC1\(windows95="simpler", jamaica=0, cardinal=Contract[A|C]\) \[\d+ gas\]
└── SYMBOL\.methodB1\(lolol="snitches_get_stiches", dynamo=111\) \[\d+ gas\]
    ├── ContractC\.getSomeList\(\) -> \[
    │     3425311345134513461345134534531452345,
    │     111344445534535353,
    │     993453434534534534534977788884443333
    │   \] \[\d+ gas\]
    └── ContractC\.methodC1\(windows95="simpler", jamaica=111, cardinal=Contract[A|C]\) \[\d+ gas\]
"""


@pytest.fixture
def local_trace():
    return LOCAL_TRACE


@pytest.fixture
def captrace(capsys):
    class CapTrace:
        def read_trace(self, expected_start: str, file=None):
            lines = file.readlines() if file else capsys.readouterr().out.splitlines()
            start_index = 0
            for index, line in enumerate(lines):
                if line.strip().startswith(expected_start):
                    start_index = index
                    break

            return lines[start_index:]

    return CapTrace()


@geth_process_test
def test_supports_tracing(geth_provider):
    assert geth_provider.supports_tracing


@geth_process_test
def test_local_transaction_traces(geth_receipt, captrace, local_trace):
    # NOTE: Strange bug in Rich where we can't use sys.stdout for testing tree output.
    # And we have to write to a file, close it, and then re-open it to see output.
    def run_test(path):
        # Use a tempfile to avoid terminal inconsistencies affecting output.
        with open(path / "temp", "w") as file:
            geth_receipt.show_trace(file=file)

        with open(path / "temp", "r") as file:
            lines = captrace.read_trace("Call trace for", file=file)
            assert_rich_output(lines, local_trace)

    run_in_tempdir(run_test)

    # Verify can happen more than once.
    run_in_tempdir(run_test, name="temp")


def assert_rich_output(rich_capture: list[str], expected: str):
    expected_lines = [x.rstrip() for x in expected.splitlines() if x.rstrip()]
    actual_lines = [x.rstrip() for x in rich_capture if x.rstrip()]
    assert actual_lines, "No output."
    output = "\n".join(actual_lines)

    for actual, expected in zip(actual_lines, expected_lines):
        fail_message = f"""\n
        \tPattern: {expected}\n
        \tLine   : {actual}\n
        \n
        Complete output:
        \n{output}
        """

        try:
            assert re.match(expected, actual), fail_message
        except AssertionError:
            raise  # Let assertion errors raise as normal.
        except Exception as err:
            pytest.fail(f"{fail_message}\n{err}")

    actual_len = len(actual_lines)
    expected_len = len(expected_lines)
    if expected_len > actual_len:
        rest = "\n".join(expected_lines[actual_len:])
        pytest.fail(f"Missing expected lines: {rest}")


@geth_process_test
def test_str_and_repr(geth_contract, geth_account, geth_provider):
    receipt = geth_contract.setNumber(10, sender=geth_account)
    trace = geth_provider.get_transaction_trace(receipt.txn_hash)
    expected = rf"{geth_contract.contract_type.name}\.setNumber\(\s*num=\d+\s*\) \[\d+ gas\]"
    for actual in (str(trace), repr(trace)):
        assert re.match(expected, actual)


@geth_process_test
def test_str_and_repr_deploy(geth_contract, geth_provider):
    creation = geth_contract.creation_metadata
    trace = geth_provider.get_transaction_trace(creation.txn_hash)
    _ = trace.enriched_calltree
    expected = rf"{geth_contract.contract_type.name}\.__new__\(\s*num=\d+\s*\) \[\d+ gas\]"
    for actual in (str(trace), repr(trace)):
        assert re.match(expected, actual), f"Unexpected repr: {actual}"


@geth_process_test
def test_str_and_repr_erigon(
    parity_trace_response, geth_provider, mock_web3, networks, mock_geth, geth_contract
):
    mock_web3.client_version = "erigon_MOCK"

    def _request(rpc, arguments):
        if rpc == "trace_transaction":
            return parity_trace_response

        return geth_provider.web3.provider.make_request(rpc, arguments)

    mock_web3.provider.make_request.side_effect = _request
    mock_web3.eth = geth_provider.web3.eth
    orig_provider = networks.active_provider
    networks.active_provider = mock_geth
    expected = r"0x[a-fA-F0-9]{40}\.0x[a-fA-F0-9]+\(\) \[\d+ gas\]"

    try:
        creation = geth_contract.creation_metadata
        trace = mock_geth.get_transaction_trace(creation.txn_hash)
        assert isinstance(trace, Trace)
        for actual in (str(trace), repr(trace)):
            assert re.match(expected, actual), actual

    finally:
        networks.active_provider = orig_provider


@geth_process_test
def test_str_multiline(geth_contract, geth_account):
    tx = geth_contract.getNestedAddressArray.transact(sender=geth_account)
    actual = f"{tx.trace}"
    expected = r"""
VyperContract\.getNestedAddressArray\(\) -> \[
    \['tx\.origin', 'tx\.origin', 'tx\.origin'\],
    \['ZERO_ADDRESS', 'ZERO_ADDRESS', 'ZERO_ADDRESS'\]
\] \[\d+ gas\]
"""
    assert re.match(expected.strip(), actual.strip())


@geth_process_test
def test_str_list_of_lists(geth_contract, geth_account):
    tx = geth_contract.getNestedArrayMixedDynamic.transact(sender=geth_account)
    actual = f"{tx.trace}"
    expected = r"""
VyperContract\.getNestedArrayMixedDynamic\(\) -> \[
    \[\[\[0\], \[0, 1\], \[0, 1, 2\]\]\],
    \[
        \[\[0\], \[0, 1\], \[0, 1, 2\]\],
        \[\[0\], \[0, 1\], \[0, 1, 2\]\]
    \],
    \[\],
    \[\],
    \[\]
\] \[\d+ gas\]
"""
    assert re.match(expected.strip(), actual.strip())


@geth_process_test
def test_get_gas_report(gas_tracker, geth_account, geth_contract):
    tx = geth_contract.setNumber(924, sender=geth_account)
    trace = tx.trace
    actual = trace.get_gas_report()
    contract_name = geth_contract.contract_type.name
    expected = {contract_name: {"setNumber": [tx.gas_used]}}
    assert actual == expected


@geth_process_test
def test_get_gas_report_deploy(gas_tracker, geth_contract):
    tx = geth_contract.creation_metadata.receipt
    trace = tx.trace
    actual = trace.get_gas_report()
    contract_name = geth_contract.contract_type.name
    expected = {contract_name: {"__new__": [tx.gas_used]}}
    assert actual == expected


@geth_process_test
def test_transaction_trace_create(vyper_contract_instance):
    tx_hash = vyper_contract_instance.creation_metadata.txn_hash
    trace = TransactionTrace(transaction_hash=tx_hash)
    actual = f"{trace}"
    expected = r"VyperContract\.__new__\(num=0\) \[\d+ gas\]"
    assert re.match(expected, actual)


@geth_process_test
def test_get_transaction_trace_erigon_calltree(
    parity_trace_response, geth_provider, mock_web3, mocker
):
    # hash defined in parity_trace_response
    tx_hash = "0x3cef4aaa52b97b6b61aa32b3afcecb0d14f7862ca80fdc76504c37a9374645c4"
    default_make_request = geth_provider.web3.provider.make_request

    def hacked_make_request(rpc, arguments):
        if rpc == "trace_transaction":
            return parity_trace_response

        return default_make_request(rpc, arguments)

    mock_web3.provider.make_request.side_effect = hacked_make_request
    original_web3 = geth_provider._web3
    geth_provider._web3 = mock_web3
    trace = geth_provider.get_transaction_trace(tx_hash, call_trace_approach=TraceApproach.PARITY)
    trace.__dict__["transaction"] = mocker.MagicMock()  # doesn't matter.
    result = trace.enriched_calltree

    # Defined in parity_mock_response
    assert result["contract_id"] == "0xC17f2C69aE2E66FD87367E3260412EEfF637F70E"
    assert result["method_id"] == "0x96d373e5"

    geth_provider._web3 = original_web3


@geth_process_test
def test_printing_debug_logs_vyper(geth_provider, geth_account, vyper_printing):
    num = 789
    # Why is 6 afraid of 7?  Because {num}
    receipt = vyper_printing.print_uint(num, sender=geth_account)
    assert receipt.status
    assert len(list(receipt.debug_logs_typed)) == 1
    assert receipt.debug_logs_typed[0][0] == num


@geth_process_test
def test_printing_debug_logs_compat(geth_provider, geth_account, vyper_printing):
    num = 456
    receipt = vyper_printing.print_uint_compat(num, sender=geth_account)
    assert receipt.status
    assert len(list(receipt.debug_logs_typed)) == 1
    assert receipt.debug_logs_typed[0][0] == num


@geth_process_test
def test_call_trace_supports_debug_trace_call(geth_contract, geth_account):
    tx = {
        "chainId": "0x539",
        "to": "0x77c7E3905c21177Be97956c6620567596492C497",
        "value": "0x0",
        "data": "0x23fd0e40",
        "type": 2,
        "accessList": [],
    }
    trace = CallTrace(tx=tx)
    _ = trace._traced_call
    assert trace.supports_debug_trace_call


@geth_process_test
def test_return_value(benchmark, geth_contract, geth_account):
    receipt = benchmark.pedantic(
        geth_contract.getFilledArray.transact,
        kwargs={"sender": geth_account},
        rounds=5,
        warmup_rounds=1,
    )
    trace = receipt.trace
    expected = [1, 2, 3]  # Hardcoded in contract
    assert receipt.return_value == expected

    # In `trace.return_value`, it is still a tuple.
    # (unlike receipt.return_value)
    actual = trace.return_value[0]
    assert actual == expected

    # NOTE: This is very important from a performance perspective!
    # (VERY IMPORTANT). We shouldn't need to enrich anything.
    assert trace._enriched_calltree is None

    # Seeing 0.14.
    # Before https://github.com/ApeWorX/ape/pull/2225, was seeing 0.17.
    # In CI, can see up to 0.4 though.
    avg = benchmark.stats["mean"]
    assert avg < 0.6


@geth_process_test
def test_return_value_tuple(geth_provider):
    """
    Tests against a bug where a trace in a certain state (HH returning a tuple) was
    unable to get the correct return_value.
    """
    transaction_hash = "0xa4803961e06c673b255ca6af78d00df3c0ebef0b2f23325a1457eaaf20914e8e"
    abi = MethodABI(
        type="function",
        name="newAccountant",
        stateMutability="nonpayable",
        inputs=[
            ABIType(name="feeManager", type="address", components=None, internal_type="address"),
            ABIType(name="feeRecipient", type="address", components=None, internal_type="address"),
            ABIType(
                name="defaultManagement", type="uint16", components=None, internal_type="uint16"
            ),
            ABIType(
                name="defaultPerformance", type="uint16", components=None, internal_type="uint16"
            ),
            ABIType(name="defaultRefund", type="uint16", components=None, internal_type="uint16"),
            ABIType(name="defaultMaxFee", type="uint16", components=None, internal_type="uint16"),
            ABIType(name="defaultMaxGain", type="uint16", components=None, internal_type="uint16"),
            ABIType(name="defaultMaxLoss", type="uint16", components=None, internal_type="uint16"),
        ],
        outputs=[
            ABIType(name="_newAccountant", type="address", components=None, internal_type="address")
        ],
    )
    calltree = {
        "call_type": "CALL",
        "address": "0x5fbdb2315678afecb367f032d93f642f64180aa3",
        "value": 0,
        "depth": 0,
        "gas_limit": None,
        "gas_cost": None,
        "calldata": "0x184ac61b000000000000000000000000f39fd6e51aad88f6f4ce6ab8827279cfffb9226600000000000000000000000015d34aaf54267db7d7c367839aaf71a00a2c6a65000000000000000000000000000000000000000000000000000000000000006400000000000000000000000000000000000000000000000000000000000003e80000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000027100000000000000000000000000000000000000000000000000000000000000000",  # noqa: E501
        "returndata": "0x000000000000000000000000a16e02e87b7454126e5e10d957a927a7f5b5d2be",
        "calls": [
            {
                "call_type": "CREATE",
                "address": "0xa16e02e87b7454126e5e10d957a927a7f5b5d2be",
                "value": 0,
                "depth": 1,
                "gas_limit": None,
                "gas_cost": None,
                "calldata": "0x",
                "returndata": "0x608060405234801561001057600080fd5b50600436106101c45760003560e01c80639b3b6955116100f9578063d0fb020311610097578063e2a85ce411610071578063e2a85ce4146104e3578063e74b981b146104f6578063f94c53c714610509578063fb9321081461051157600080fd5b8063d0fb02031461049d578063d8609c5b146104b0578063de1eb9a3146104c357600080fd5b8063b53d68e5116100d3578063b53d68e51461043b578063b543503e14610444578063c7c504b914610457578063ceb68c231461048a57600080fd5b80639b3b6955146103a85780639e09ed5f146103bb578063a622ee7c1461040857600080fd5b806363453ae11161016657806382e4dd6f1161014057806382e4dd6f1461033f5780638a4adf241461035a578063921f8a8f1461036d578063962941781461039557600080fd5b806363453ae11461027157806367bee7e9146102845780637b5d7b651461029757600080fd5b8063256b5a02116101a2578063256b5a021461022157806346904840146102345780635783fe39146102475780635cece03a1461025e57600080fd5b8063015cf150146101c957806303579dca146101f957806324be66281461020e575b600080fd5b6004546101dc906001600160a01b031681565b6040516001600160a01b0390911681526020015b60405180910390f35b61020c610207366004611ea3565b610524565b005b61020c61021c366004611ec7565b610595565b61020c61022f366004611ea3565b610622565b6002546101dc906001600160a01b031681565b61025060005481565b6040519081526020016101f0565b61020c61026c366004611ee0565b6106e3565b61020c61027f366004611ea3565b610757565b61020c610292366004611ea3565b6107c5565b6102fa6102a5366004611ea3565b60076020526000908152604090205461ffff80821691620100008104821691600160201b8204811691600160301b8104821691600160401b8204811691600160501b810490911690600160601b900460ff1687565b6040805161ffff988916815296881660208801529487169486019490945291851660608501528416608084015290921660a082015290151560c082015260e0016101f0565b61034760c881565b60405161ffff90911681526020016101f0565b6003546101dc906001600160a01b031681565b61038061037b366004611f19565b610886565b604080519283526020830191909152016101f0565b61020c6103a3366004611f4e565b610d90565b61020c6103b6366004611ea3565b610e20565b6005546102fa9061ffff80821691620100008104821691600160201b8204811691600160301b8104821691600160401b8204811691600160501b810490911690600160601b900460ff1687565b61042b610416366004611ea3565b60066020526000908152604090205460ff1681565b60405190151581526020016101f0565b61034761138881565b61020c610452366004611ea3565b610eb7565b61042b610465366004611ea3565b6001600160a01b0316600090815260076020526040902054600160601b900460ff1690565b61020c610498366004611ea3565b610f09565b6001546101dc906001600160a01b031681565b61020c6104be366004611f8c565b6110b4565b6104d66104d1366004611ea3565b61138f565b6040516101f09190612014565b61020c6104f1366004612074565b6114cf565b61020c610504366004611ea3565b6114ed565b61020c61158c565b61020c61051f366004611f4e565b611631565b6040516370a0823160e01b81523060048201526105929082906001600160a01b038216906370a0823190602401602060405180830381865afa15801561056e573d6000803e3d6000fd5b505050506040513d601f19601f820116820180604052508101906103a391906120e8565b50565b61059d61168e565b6127108111156105e75760405162461bcd60e51b815260206004820152601060248201526f686967686572207468616e203130302560801b60448201526064015b60405180910390fd5b60008190556040518181527f18182e268b61d2aada98f23ade23b0ea133d5b0b6712dbfa682dc6da29941c229060200160405180910390a150565b61062a6116d9565b6001600160a01b03811660009081526006602052604090205460ff16156106835760405162461bcd60e51b815260206004820152600d60248201526c185b1c9958591e481859191959609a1b60448201526064016105de565b6001600160a01b03811660008181526006602052604090819020805460ff1916600190811790915590517fce96c4db32686d3f0011df1abea0ab6c5794b848868dcbece79961fef7e8198d916106d891612101565b60405180910390a250565b6106eb61168e565b6001600160a01b03821660009081526006602052604090205460ff166107235760405162461bcd60e51b81526004016105de90612129565b6001600160a01b0391821660009081526008602090815260408083209390941682529190915220805460ff19166001179055565b6040516370a0823160e01b81523060048201526105929082906001600160a01b038216906370a0823190602401602060405180830381865afa1580156107a1573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061051f91906120e8565b6107cd61168e565b6001600160a01b038116600090815260076020526040902054600160601b900460ff166108315760405162461bcd60e51b8152602060048201526012602482015271139bc818dd5cdd1bdb481999595cc81cd95d60721b60448201526064016105de565b6001600160a01b03811660008181526007602052604080822080546cffffffffffffffffffffffffff19169055517f3e6648a1d6918f893e09d7f2a385f04bdafbf8ad899b255b7f40e02c967b55879190a250565b600080610891611739565b33600090815260076020908152604091829020825160e081018452905461ffff8082168352620100008204811693830193909352600160201b8104831693820193909352600160301b830482166060820152600160401b830482166080820152600160501b830490911660a0820152600160601b90910460ff16151560c0820181905261098957506040805160e08101825260055461ffff808216835262010000820481166020840152600160201b8204811693830193909352600160301b810483166060830152600160401b810483166080830152600160501b810490921660a0820152600160601b90910460ff16151560c08201525b6040516339ebf82360e01b81526001600160a01b038716600482015260009033906339ebf82390602401608060405180830381865afa1580156109d0573d6000803e3d6000fd5b505050506040513d601f19601f820116820180604052508101906109f49190612152565b825190915061ffff1615610a59576000816020015142610a1491906121dc565b90506301e18558612710846000015161ffff16838560400151610a3791906121ef565b610a4191906121ef565b610a4b9190612206565b610a559190612206565b9450505b8515610b5f573360009081526008602090815260408083206001600160a01b038b16845290915290205460ff1615610abb573360009081526008602090815260408083206001600160a01b038b1684529091529020805460ff19169055610b2d565b608082015161ffff1615610b2d57612710826080015161ffff168260400151610ae491906121ef565b610aee9190612206565b861115610b2d5760405162461bcd60e51b815260206004820152600d60248201526c3a37b79036bab1b41033b0b4b760991b60448201526064016105de565b612710826020015161ffff1687610b4491906121ef565b610b4e9190612206565b610b589085612228565b9350610d4b565b3360009081526008602090815260408083206001600160a01b038b16845290915290205460ff1615610bbb573360009081526008602090815260408083206001600160a01b038b1684529091529020805460ff19169055610c31565b6127108260a0015161ffff161015610c31576127108260a0015161ffff168260400151610be891906121ef565b610bf29190612206565b851115610c315760405162461bcd60e51b815260206004820152600d60248201526c746f6f206d756368206c6f737360981b60448201526064016105de565b604082015161ffff1615610d4b576000336001600160a01b03166338d52e0f6040518163ffffffff1660e01b8152600401602060405180830381865afa158015610c7f573d6000803e3d6000fd5b505050506040513d601f19601f82011682018060405250810190610ca3919061223b565b9050610d36612710846040015161ffff1688610cbf91906121ef565b610cc99190612206565b6040516370a0823160e01b81523060048201526001600160a01b038416906370a0823190602401602060405180830381865afa158015610d0d573d6000803e3d6000fd5b505050506040513d601f19601f82011682018060405250810190610d3191906120e8565b611768565b93508315610d4957610d49338286611782565b505b606082015161ffff1615610d8657610d83612710836060015161ffff1688610d7391906121ef565b610d7d9190612206565b85611768565b93505b5050935093915050565b610d9861168e565b600054604051639f40a7b360e01b8152600481018390523060248201819052604482015260648101919091526001600160a01b03831690639f40a7b3906084016020604051808303816000875af1158015610df7573d6000803e3d6000fd5b505050506040513d601f19601f82011682018060405250810190610e1b91906120e8565b505050565b610e2861168e565b6001600160a01b038116610e6d5760405162461bcd60e51b815260206004820152600c60248201526b5a45524f204144445245535360a01b60448201526064016105de565b600480546001600160a01b0319166001600160a01b0383169081179091556040517fa839c45565e8a86de41783841928f4acde049c2b7160f0ea4d4698220c5af61b90600090a250565b610ebf61168e565b600380546001600160a01b0319166001600160a01b0383169081179091556040517fda833a9122ed0b27d5c78c99315bb3758f1b77fb240db484a67fd0f286b263e590600090a250565b610f116116d9565b6001600160a01b03811660009081526006602052604090205460ff16610f655760405162461bcd60e51b81526020600482015260096024820152681b9bdd08185919195960ba1b60448201526064016105de565b6000816001600160a01b03166338d52e0f6040518163ffffffff1660e01b8152600401602060405180830381865afa158015610fa5573d6000803e3d6000fd5b505050506040513d601f19601f82011682018060405250810190610fc9919061223b565b604051636eb1769f60e11b81523060048201526001600160a01b0384811660248301529192509082169063dd62ed3e90604401602060405180830381865afa158015611019573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061103d91906120e8565b15611057576110576001600160a01b038216836000611820565b6001600160a01b03821660008181526006602052604090819020805460ff19169055517fce96c4db32686d3f0011df1abea0ab6c5794b848868dcbece79961fef7e8198d906110a890600290612101565b60405180910390a25050565b6110bc61168e565b6001600160a01b03871660009081526006602052604090205460ff166110f45760405162461bcd60e51b81526004016105de90612129565b60c861ffff871611156111445760405162461bcd60e51b81526020600482015260186024820152771b585b9859d95b595b9d08199959481d1a1c995cda1bdb1960421b60448201526064016105de565b61138861ffff861611156111965760405162461bcd60e51b81526020600482015260196024820152781c195c999bdc9b585b98d948199959481d1a1c995cda1bdb19603a1b60448201526064016105de565b6127108161ffff1611156111d75760405162461bcd60e51b81526020600482015260086024820152670e8dede40d0d2ced60c31b60448201526064016105de565b60006040518060e001604052808861ffff1681526020018761ffff1681526020018661ffff1681526020018561ffff1681526020018461ffff1681526020018361ffff16815260200160011515815250905080600760008a6001600160a01b03166001600160a01b0316815260200190815260200160002060008201518160000160006101000a81548161ffff021916908361ffff16021790555060208201518160000160026101000a81548161ffff021916908361ffff16021790555060408201518160000160046101000a81548161ffff021916908361ffff16021790555060608201518160000160066101000a81548161ffff021916908361ffff16021790555060808201518160000160086101000a81548161ffff021916908361ffff16021790555060a082015181600001600a6101000a81548161ffff021916908361ffff16021790555060c082015181600001600c6101000a81548160ff021916908315150217905550905050876001600160a01b03167fff2b689837652b4795317128d1dd57305f04ec90d567ff4b921424f1a19e8b0a8260405161137d9190612014565b60405180910390a25050505050505050565b6040805160e081018252600080825260208201819052918101829052606081018290526080810182905260a0810182905260c0810191909152506001600160a01b038116600090815260076020908152604091829020825160e081018452905461ffff8082168352620100008204811693830193909352600160201b8104831693820193909352600160301b830482166060820152600160401b830482166080820152600160501b830490911660a0820152600160601b90910460ff16151560c082018190526114ca57506040805160e08101825260055461ffff808216835262010000820481166020840152600160201b8204811693830193909352600160301b810483166060830152600160401b810483166080830152600160501b810490921660a0820152600160601b90910460ff16151560c08201525b919050565b6114d761168e565b6114e5868686868686611968565b505050505050565b6114f561168e565b6001600160a01b03811661153a5760405162461bcd60e51b815260206004820152600c60248201526b5a45524f204144445245535360a01b60448201526064016105de565b600280546001600160a01b038381166001600160a01b0319831681179093556040519116919082907fb03f92c8c7ac39710f28b146f754650929499d599a66d51423cbd7f3ceb9aee390600090a35050565b6004546001600160a01b031633146115df5760405162461bcd60e51b81526020600482015260166024820152753737ba10333aba3ab932903332b29036b0b730b3b2b960511b60448201526064016105de565b60048054600180546001600160a01b03199081166001600160a01b0384161790915516905560405133907f772ddcfc9a0f3b1401c0f60000a81999005d9d593b71bb67707c5f326eb7c94d90600090a2565b611639611b9d565b600254611653906001600160a01b03848116911683611bf9565b816001600160a01b03167f962bc326c7b063c70721a63687e0e19450155f93c58eca94769746c0cfb02c5d826040516110a891815260200190565b6001546001600160a01b031633146116d75760405162461bcd60e51b815260206004820152600c60248201526b10b332b29036b0b730b3b2b960a11b60448201526064016105de565b565b6001546001600160a01b03163314806116fc57506003546001600160a01b031633145b6116d75760405162461bcd60e51b815260206004820152600e60248201526d10bb30bab63a1036b0b730b3b2b960911b60448201526064016105de565b3360009081526006602052604090205460ff166116d75760405162461bcd60e51b81526004016105de90612129565b60008183106117775781611779565b825b90505b92915050565b604051636eb1769f60e11b81523060048201526001600160a01b03848116602483015282919084169063dd62ed3e90604401602060405180830381865afa1580156117d1573d6000803e3d6000fd5b505050506040513d601f19601f820116820180604052508101906117f591906120e8565b1015610e1b576118106001600160a01b038316846000611820565b610e1b6001600160a01b03831684835b80158061189a5750604051636eb1769f60e11b81523060048201526001600160a01b03838116602483015284169063dd62ed3e90604401602060405180830381865afa158015611874573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061189891906120e8565b155b6119055760405162461bcd60e51b815260206004820152603660248201527f5361666545524332303a20617070726f76652066726f6d206e6f6e2d7a65726f60448201527520746f206e6f6e2d7a65726f20616c6c6f77616e636560501b60648201526084016105de565b6040516001600160a01b038316602482015260448101829052610e1b90849063095ea7b360e01b906064015b60408051601f198184030181529190526020810180516001600160e01b03166001600160e01b031990931692909217909152611c29565b60c861ffff871611156119b85760405162461bcd60e51b81526020600482015260186024820152771b585b9859d95b595b9d08199959481d1a1c995cda1bdb1960421b60448201526064016105de565b61138861ffff86161115611a0a5760405162461bcd60e51b81526020600482015260196024820152781c195c999bdc9b585b98d948199959481d1a1c995cda1bdb19603a1b60448201526064016105de565b6127108161ffff161115611a4b5760405162461bcd60e51b81526020600482015260086024820152670e8dede40d0d2ced60c31b60448201526064016105de565b6040805160e0808201835261ffff89811680845289821660208086018290528a84168688018190528a851660608089018290528b87166080808b018290528c891660a0808d01829052600060c09d8e018190526005805463ffffffff1916909b1762010000909a029990991767ffffffff000000001916600160201b90970267ffff000000000000191696909617600160301b909502949094176bffffffff00000000000000001916600160401b90920261ffff60501b191691909117600160501b9093029290921760ff60601b19811690965589518688168152601087901c8816818601529386901c8716848b0152603086901c8716908401529784901c85169782019790975260509290921c90921694810194909452918301919091527fbbcfba7e6e61ab9dbbe4ee1512e1e0c0ff1b236ba707ef51c8f45e7af433b89d910160405180910390a1505050505050565b6002546001600160a01b0316331480611bc057506001546001600160a01b031633145b6116d75760405162461bcd60e51b815260206004820152600a602482015269085c9958da5c1a595b9d60b21b60448201526064016105de565b6040516001600160a01b038316602482015260448101829052610e1b90849063a9059cbb60e01b90606401611931565b6000611c7e826040518060400160405280602081526020017f5361666545524332303a206c6f772d6c6576656c2063616c6c206661696c6564815250856001600160a01b0316611cfe9092919063ffffffff16565b9050805160001480611c9f575080806020019051810190611c9f9190612258565b610e1b5760405162461bcd60e51b815260206004820152602a60248201527f5361666545524332303a204552433230206f7065726174696f6e20646964206e6044820152691bdd081cdd58d8d9595960b21b60648201526084016105de565b6060611d0d8484600085611d15565b949350505050565b606082471015611d765760405162461bcd60e51b815260206004820152602660248201527f416464726573733a20696e73756666696369656e742062616c616e636520666f6044820152651c8818d85b1b60d21b60648201526084016105de565b600080866001600160a01b03168587604051611d92919061229e565b60006040518083038185875af1925050503d8060008114611dcf576040519150601f19603f3d011682016040523d82523d6000602084013e611dd4565b606091505b5091509150611de587838387611df0565b979650505050505050565b60608315611e5f578251600003611e58576001600160a01b0385163b611e585760405162461bcd60e51b815260206004820152601d60248201527f416464726573733a2063616c6c20746f206e6f6e2d636f6e747261637400000060448201526064016105de565b5081611d0d565b611d0d8383815115611e745781518083602001fd5b8060405162461bcd60e51b81526004016105de91906122ba565b6001600160a01b038116811461059257600080fd5b600060208284031215611eb557600080fd5b8135611ec081611e8e565b9392505050565b600060208284031215611ed957600080fd5b5035919050565b60008060408385031215611ef357600080fd5b8235611efe81611e8e565b91506020830135611f0e81611e8e565b809150509250929050565b600080600060608486031215611f2e57600080fd5b8335611f3981611e8e565b95602085013595506040909401359392505050565b60008060408385031215611f6157600080fd5b8235611f6c81611e8e565b946020939093013593505050565b803561ffff811681146114ca57600080fd5b600080600080600080600060e0888a031215611fa757600080fd5b8735611fb281611e8e565b9650611fc060208901611f7a565b9550611fce60408901611f7a565b9450611fdc60608901611f7a565b9350611fea60808901611f7a565b9250611ff860a08901611f7a565b915061200660c08901611f7a565b905092959891949750929550565b600060e08201905061ffff8084511683528060208501511660208401528060408501511660408401528060608501511660608401528060808501511660808401528060a08501511660a08401525060c0830151151560c083015292915050565b60008060008060008060c0878903121561208d57600080fd5b61209687611f7a565b95506120a460208801611f7a565b94506120b260408801611f7a565b93506120c060608801611f7a565b92506120ce60808801611f7a565b91506120dc60a08801611f7a565b90509295509295509295565b6000602082840312156120fa57600080fd5b5051919050565b602081016003831061212357634e487b7160e01b600052602160045260246000fd5b91905290565b6020808252600f908201526e1d985d5b1d081b9bdd081859191959608a1b604082015260600190565b60006080828403121561216457600080fd5b6040516080810181811067ffffffffffffffff8211171561219557634e487b7160e01b600052604160045260246000fd5b8060405250825181526020830151602082015260408301516040820152606083015160608201528091505092915050565b634e487b7160e01b600052601160045260246000fd5b8181038181111561177c5761177c6121c6565b808202811582820484141761177c5761177c6121c6565b60008261222357634e487b7160e01b600052601260045260246000fd5b500490565b8082018082111561177c5761177c6121c6565b60006020828403121561224d57600080fd5b8151611ec081611e8e565b60006020828403121561226a57600080fd5b81518015158114611ec057600080fd5b60005b8381101561229557818101518382015260200161227d565b50506000910152565b600082516122b081846020870161227a565b9190910192915050565b60208152600082518060208401526122d981604085016020870161227a565b601f01601f1916919091016040019291505056fea26469706673582212206c39a04ece4b6c74500d141c33f45c15a39c48bef7ac5111ccc582306f6d41d964736f6c63430008120033",  # noqa: E501
                "calls": [],
                "selfdestruct": False,
                "failed": False,
                "events": [
                    {
                        "call_type": "EVENT",
                        "data": "0x000000000000000000000000000000000000000000000000000000000000006400000000000000000000000000000000000000000000000000000000000003e800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000271000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",  # noqa: E501
                        "depth": 2,
                        "topics": [
                            "0xbbcfba7e6e61ab9dbbe4ee1512e1e0c0ff1b236ba707ef51c8f45e7af433b89d"
                        ],
                    }
                ],
            }
        ],
        "selfdestruct": False,
        "failed": False,
        "events": [
            {
                "call_type": "EVENT",
                "data": "0x",
                "depth": 1,
                "topics": [
                    "0x111fcf41d7f010b6acebbb070fcf96056db140c08d3e7cd9cff07789d93b1e4c",
                    "0x000000000000000000000000a16e02e87b7454126e5e10d957a927a7f5b5d2be",
                ],
            }
        ],
    }
    transaction = {
        "chainId": 31337,
        "to": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
        "from": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "gas": 30000000,
        "nonce": 1,
        "value": 0,
        "data": "0x184ac61b000000000000000000000000f39fd6e51aad88f6f4ce6ab8827279cfffb9226600000000000000000000000015d34aaf54267db7d7c367839aaf71a00a2c6a65000000000000000000000000000000000000000000000000000000000000006400000000000000000000000000000000000000000000000000000000000003e80000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000027100000000000000000000000000000000000000000000000000000000000000000",  # noqa: E501
        "type": 2,
        "maxFeePerGas": 0,
        "maxPriorityFeePerGas": 0,
        "accessList": [],
        "block_number": 2,
        "gas_used": 1931665,
        "logs": [
            {
                "address": "0xa16E02E87b7454126E5E10d957A927A7F5B5d2be",
                "blockHash": HexBytes(
                    "0x43c010ce0d9452289205c88a180520e9670bdf6f84d21b8c35d7c815136bba78"
                ),
                "blockNumber": 2,
                "data": HexBytes(
                    "0x000000000000000000000000000000000000000000000000000000000000006400000000000000000000000000000000000000000000000000000000000003e800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000271000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"  # noqa: E501
                ),
                "logIndex": 0,
                "removed": False,
                "topics": [
                    HexBytes("0xbbcfba7e6e61ab9dbbe4ee1512e1e0c0ff1b236ba707ef51c8f45e7af433b89d")
                ],
                "transactionHash": HexBytes(
                    "0xa4803961e06c673b255ca6af78d00df3c0ebef0b2f23325a1457eaaf20914e8e"
                ),
                "transactionIndex": 0,
            },
            {
                "address": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
                "blockHash": HexBytes(
                    "0x43c010ce0d9452289205c88a180520e9670bdf6f84d21b8c35d7c815136bba78"
                ),
                "blockNumber": 2,
                "data": HexBytes("0x"),
                "logIndex": 1,
                "removed": False,
                "topics": [
                    HexBytes("0x111fcf41d7f010b6acebbb070fcf96056db140c08d3e7cd9cff07789d93b1e4c"),
                    HexBytes("0x000000000000000000000000a16e02e87b7454126e5e10d957a927a7f5b5d2be"),
                ],
                "transactionHash": HexBytes(
                    "0xa4803961e06c673b255ca6af78d00df3c0ebef0b2f23325a1457eaaf20914e8e"
                ),
                "transactionIndex": 0,
            },
        ],
        "status": 1,
        "txn_hash": "0xa4803961e06c673b255ca6af78d00df3c0ebef0b2f23325a1457eaaf20914e8e",
        "transaction": {
            "chainId": 31337,
            "to": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
            "from": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
            "gas": 30000000,
            "nonce": 1,
            "value": 0,
            "data": "0x184ac61b000000000000000000000000f39fd6e51aad88f6f4ce6ab8827279cfffb9226600000000000000000000000015d34aaf54267db7d7c367839aaf71a00a2c6a65000000000000000000000000000000000000000000000000000000000000006400000000000000000000000000000000000000000000000000000000000003e80000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000027100000000000000000000000000000000000000000000000000000000000000000",  # noqa: E501
            "type": 2,
            "max_fee": 0,
            "max_priority_fee": 0,
        },
        "gas_limit": 30000000,
        "gas_price": 0,
    }

    class TraceForTest(TransactionTrace):
        @property
        def transaction(self) -> dict:
            return transaction

        def get_raw_calltree(self) -> dict:
            return calltree

        @property
        def root_method_abi(self) -> Optional[MethodABI]:
            return abi

    trace = TraceForTest(transaction_hash=transaction_hash)
    trace.call_trace_approach = TraceApproach.GETH_STRUCT_LOG_PARSE

    actual = trace.return_value
    expected = ("0xa16E02E87b7454126E5E10d957A927A7F5B5d2be",)
    assert actual == expected
